# services/prediction_review.py
"""Track predictions and evaluate them after the horizon window (candle-based MFE/MAE)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd

from db.models import DetectedSignal, MarketVerification, PredictionReview
from db.session import SessionLocal
from engine.confluence import ACTION_BUY, ACTION_NO_TRADE, ACTION_SELL, ACTION_WAIT
from engine.data import get_data
from services.feedback_fields import split_feedback_fields
from services.training_service import reconcile_training_record
from services.user_access import FEEDBACK_DUE_HOURS
from utils import settings
from utils.config import INTERVAL as DEFAULT_INTERVAL
from utils.logger import get_logger

log = get_logger("services.prediction_review")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "snapshots")
MAX_VERIFY_RETRIES = int(os.getenv("PREDICTION_VERIFY_MAX_RETRIES", "5"))

NON_TRADE_ACTIONS = frozenset({
    ACTION_NO_TRADE,
    ACTION_WAIT,
    "NO_TRADE",
    "WAIT_FOR_CONFIRMATION",
})


def is_trade_signal(action: str | None) -> bool:
    return bool(action and action not in NON_TRADE_ACTIONS)


HORIZON_HOURS = {
    "scalping": 1,
    "intraday": 4,
    "swing": 24,
}

BULLISH_ACTIONS = frozenset({ACTION_BUY, "BUY", "BUY_BIAS"})
BEARISH_ACTIONS = frozenset({ACTION_SELL, "SELL", "SELL_BIAS"})
NON_TRADE_ACTIONS = frozenset({ACTION_NO_TRADE, ACTION_WAIT, "NO_TRADE"})


def parse_horizon(raw: str | None) -> tuple[str, int]:
    key = (raw or "intraday").strip().lower()
    if key not in HORIZON_HOURS:
        key = "intraday"
    return key, HORIZON_HOURS[key]


def _atr_fraction_threshold(entry: float, atr: float, *, sideways_atr_multiplier: float | None = None) -> float:
    frac = sideways_atr_multiplier if sideways_atr_multiplier is not None else settings.get_float("verification_atr_fraction", 0.25)
    if entry <= 0:
        return 0.0005
    return (frac * atr) / entry


def _direction_from_change(change: float, threshold: float) -> str:
    if change > threshold:
        return "UP"
    if change < -threshold:
        return "DOWN"
    return "SIDEWAYS"


def verify_candles(
    candles: pd.DataFrame,
    *,
    entry: float,
    invalidation: float | None,
    target: float | None,
    predicted_action: str,
    atr: float,
    sideways_atr_multiplier: float | None = None,
) -> dict:
    """Candle-based MFE/MAE with invalidation-first logic."""
    if candles.empty or entry <= 0:
        raise ValueError("Insufficient candle data for verification")

    threshold = _atr_fraction_threshold(entry, atr, sideways_atr_multiplier=sideways_atr_multiplier)
    mfe = 0.0
    mae = 0.0
    invalidation_hit = False
    is_bull = predicted_action in BULLISH_ACTIONS
    is_bear = predicted_action in BEARISH_ACTIONS

    for _, row in candles.iterrows():
        high = float(row["High"])
        low = float(row["Low"])
        if is_bull:
            fav = high - entry
            adv = entry - low
            if invalidation is not None and low <= invalidation:
                invalidation_hit = True
                mae = max(mae, adv)
                break
            if target is not None and high >= target:
                mfe = max(mfe, fav)
                break
        elif is_bear:
            fav = entry - low
            adv = high - entry
            if invalidation is not None and high >= invalidation:
                invalidation_hit = True
                mae = max(mae, adv)
                break
            if target is not None and low <= target:
                mfe = max(mfe, fav)
                break
        else:
            fav_up = high - entry
            fav_down = entry - low
            mfe = max(mfe, fav_up, fav_down)
            mae = max(mae, abs(entry - low), abs(high - entry))
            continue
        mfe = max(mfe, fav)
        mae = max(mae, adv)

    end_price = float(candles["Close"].iloc[-1])
    change = (end_price - entry) / entry
    if invalidation_hit and (is_bull or is_bear):
        actual_direction = "INVALIDATED"
    else:
        actual_direction = _direction_from_change(change, threshold)

    if predicted_action in NON_TRADE_ACTIONS:
        outcome = "NO_TRADE_CONFIRMED" if actual_direction == "SIDEWAYS" else "NEUTRAL"
        was_correct = actual_direction == "SIDEWAYS"
    elif invalidation_hit:
        outcome = "AI_WRONG"
        was_correct = False
    elif is_bull:
        if actual_direction == "UP":
            outcome = "AI_CORRECT"
            was_correct = True
        elif actual_direction == "DOWN":
            outcome = "AI_WRONG"
            was_correct = False
        else:
            outcome = "NEUTRAL"
            was_correct = None
    elif is_bear:
        if actual_direction == "DOWN":
            outcome = "AI_CORRECT"
            was_correct = True
        elif actual_direction == "UP":
            outcome = "AI_WRONG"
            was_correct = False
        else:
            outcome = "NEUTRAL"
            was_correct = None
    else:
        outcome = "NEUTRAL"
        was_correct = None

    return {
        "start_price": entry,
        "end_price": end_price,
        "max_favorable_excursion": round(mfe, 6),
        "max_adverse_excursion": round(mae, 6),
        "actual_direction": actual_direction,
        "outcome": outcome,
        "invalidation_hit": invalidation_hit,
        "was_correct": was_correct,
    }


def _save_snapshot(review_id: int, df: pd.DataFrame, limit: int = 50) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"{review_id}.json")
    tail = df.tail(limit)
    records = []
    for ts, row in tail.iterrows():
        records.append({
            "time": str(ts),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0)),
        })
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh)
    return path


def _persist_detected_signals(db, review_id: int, signals: list[dict]):
    for sig in signals:
        db.add(DetectedSignal(
            prediction_id=review_id,
            name=sig.get("name", "unknown"),
            framework=sig.get("framework", "SMC"),
            direction=sig.get("direction"),
            timeframe=sig.get("timeframe"),
            strength=int(sig.get("strength", 0)),
            confidence=float(sig.get("confidence", 0)),
            price_low=sig.get("price_low"),
            price_high=sig.get("price_high"),
            candle_start=sig.get("candle_start"),
            candle_end=sig.get("candle_end"),
            validation_reason=sig.get("validation_reason"),
            invalidation_reason=sig.get("invalidation_reason"),
            status=sig.get("status", "active"),
        ))


def create_review(
    *,
    signal_id: int | None,
    user_id: int | None,
    symbol: str,
    interval: str,
    predicted_action: str,
    predicted_confidence: float,
    entry_price: float,
    features: dict | None = None,
    horizon: str = "intraday",
    direction: str | None = None,
    invalidation_price: float | None = None,
    target_price: float | None = None,
    component_scores: dict | None = None,
    signals: list[dict] | None = None,
    strategy_mode: str = "both",
    model_version: str | None = None,
    model_version_id: int | None = None,
    meta_ml_probability: float | None = None,
    confidence_before_ml: float | None = None,
    final_confidence: float | None = None,
    trading_style: str = "intraday",
    rule_engine_version: str | None = None,
    feature_schema_version: str | None = None,
    threshold_version_id: int | None = None,
    snapshot_df: pd.DataFrame | None = None,
    snapshot_records: list[dict] | None = None,
    source: str = "web",
) -> PredictionReview | None:
    db = SessionLocal()
    try:
        horizon_key, horizon_hours = parse_horizon(horizon)
        now = datetime.utcnow()
        due = now + timedelta(hours=FEEDBACK_DUE_HOURS)
        evaluate_at = now + timedelta(hours=horizon_hours)
        entry = float(entry_price or 0)
        if entry <= 0 and predicted_action not in NON_TRADE_ACTIONS:
            entry = 0.0

        row = PredictionReview(
            signal_id=signal_id,
            user_id=user_id,
            symbol=symbol.upper(),
            interval=interval,
            horizon=horizon_key,
            predicted_action=predicted_action.upper(),
            direction=direction,
            predicted_confidence=predicted_confidence,
            entry_price=entry,
            invalidation_price=invalidation_price,
            target_price=target_price,
            scores_json=json.dumps(component_scores or {}),
            signals_json=json.dumps(signals or []),
            strategy_mode=strategy_mode,
            model_version=model_version,
            model_version_id=model_version_id,
            threshold_version_id=threshold_version_id,
            meta_ml_probability=meta_ml_probability,
            confidence_before_ml=confidence_before_ml,
            final_confidence=final_confidence,
            trading_style=trading_style,
            rule_engine_version=rule_engine_version or "v1",
            feature_schema_version=feature_schema_version or "v1",
            predicted_at=now,
            feedback_due_at=due,
            feedback_reminder_sent=False,
            evaluate_at=evaluate_at,
            features_json=json.dumps(features or {}),
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        if signals:
            _persist_detected_signals(db, row.id, signals)
            db.commit()

        if snapshot_df is not None and not snapshot_df.empty:
            row.snapshot_path = _save_snapshot(row.id, snapshot_df)
            db.commit()
        elif snapshot_records:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            path = os.path.join(SNAPSHOT_DIR, f"{row.id}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snapshot_records, fh)
            row.snapshot_path = path
            db.commit()

        # The commits above expire the row's attributes; reload them and
        # detach cleanly so callers can read .id etc. after the session
        # closes (otherwise: DetachedInstanceError -> web /analyze 500s).
        db.refresh(row)
        db.expunge(row)
        return row
    except Exception:
        log.exception("Failed to create prediction review")
        db.rollback()
        return None
    finally:
        db.close()


def verify_single_review(review_id: int) -> bool:
    """Run candle verification for one review (used after feedback or on schedule)."""
    db = SessionLocal()
    try:
        row = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        if not row or row.status not in ("pending", "awaiting_feedback"):
            return False
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        if not row or row.status not in ("pending", "awaiting_feedback"):
            return False

        try:
            horizon_key, horizon_hours = parse_horizon(row.horizon)
            df, _ = get_data(row.symbol, row.interval, fetch=True)
            predicted_at = row.predicted_at or datetime.utcnow()
            horizon_end = predicted_at + timedelta(hours=horizon_hours)
            window = df[(df.index >= pd.Timestamp(predicted_at)) & (df.index <= pd.Timestamp(horizon_end))]
            if window.empty:
                window = df[df.index >= pd.Timestamp(predicted_at)]
            if window.empty:
                window = df.tail(max(10, horizon_hours * 4))
            atr = float((window["High"] - window["Low"]).mean()) if len(window) else 0.001
            from services.threshold_service import resolve_thresholds_model
            v_thresholds = resolve_thresholds_model(row.symbol, row.interval, row.horizon or "intraday")
            result = verify_candles(
                window,
                entry=row.entry_price or float(window["Close"].iloc[0]),
                invalidation=row.invalidation_price,
                target=row.target_price,
                predicted_action=row.predicted_action,
                atr=atr,
                sideways_atr_multiplier=v_thresholds.verification.sideways_threshold_atr_multiplier,
            )
        except Exception as exc:
            row.retry_count = (row.retry_count or 0) + 1
            if row.retry_count >= MAX_VERIFY_RETRIES:
                row.status = "verification_failed"
                row.evaluated_at = datetime.utcnow()
            db.commit()
            log.warning("Review %s verification failed (retry %s): %s", row.id, row.retry_count, exc)
            return False

        existing_mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == row.id).first()
        if not existing_mv:
            db.add(MarketVerification(
                prediction_id=row.id,
                start_price=result["start_price"],
                end_price=result["end_price"],
                max_favorable_excursion=result["max_favorable_excursion"],
                max_adverse_excursion=result["max_adverse_excursion"],
                actual_direction=result["actual_direction"],
                outcome=result["outcome"],
                invalidation_hit=result["invalidation_hit"],
                verified_at=datetime.utcnow(),
                method="candle_mfe_mae",
            ))

        row.actual_price = result["end_price"]
        row.actual_direction = result["actual_direction"]
        row.was_correct = result["was_correct"]
        row.evaluated_at = datetime.utcnow()
        row.status = "evaluated"
        db.commit()

        features = json.loads(row.features_json) if row.features_json else {}
        reconcile_training_record(row.id, features=features, predicted_action=row.predicted_action)
        log.info(
            "Review %s verified: outcome %s (dir=%s)",
            row.id, result["outcome"], result["actual_direction"],
        )
        return True
    finally:
        db.close()


def evaluate_due_reviews() -> int:
    """Process reviews whose 2h verification window has passed."""
    db = SessionLocal()
    try:
        due = (
            db.query(PredictionReview)
            .filter(
                PredictionReview.status.in_(("pending", "awaiting_feedback")),
                PredictionReview.evaluate_at <= datetime.utcnow(),
            )
            .all()
        )
        ids = [r.id for r in due]
    finally:
        db.close()

    count = 0
    for rid in ids:
        if verify_single_review(rid):
            count += 1
    return count


def list_reviews(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    *,
    symbol: str | None = None,
    conflicts_only: bool = False,
    correct_only: bool = False,
) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(PredictionReview).order_by(PredictionReview.id.desc())
        if status:
            q = q.filter(PredictionReview.status == status)
        if user_id is not None:
            q = q.filter(PredictionReview.user_id == user_id)
        if symbol:
            q = q.filter(PredictionReview.symbol == symbol.upper())
        rows = q.limit(limit * 3 if conflicts_only or correct_only else limit).all()
        out = []
        for r in rows:
            scores = json.loads(r.scores_json) if r.scores_json else {}
            uf = r.user_feedback
            mv = r.market_verification
            feedback_due = r.feedback_due_at or r.evaluate_at
            trade_entry, outcome = split_feedback_fields(uf)
            can_record_entry = is_trade_signal(r.predicted_action) and not trade_entry
            can_record_outcome = (
                is_trade_signal(r.predicted_action)
                and not outcome
                and trade_entry != "DID_NOT_TAKE"
            )
            tr = r.training_record
            conflict = tr.conflict if tr else False
            if conflicts_only and not conflict:
                continue
            if correct_only and r.was_correct is not True:
                continue
            out.append({
                "id": r.id,
                "signal_id": r.signal_id,
                "user_id": r.user_id,
                "symbol": r.symbol,
                "interval": r.interval or DEFAULT_INTERVAL,
                "horizon": r.horizon,
                "trading_style": r.trading_style or r.horizon or "intraday",
                "strategy_mode": r.strategy_mode or "both",
                "predicted_action": r.predicted_action,
                "direction": r.direction,
                "predicted_confidence": r.predicted_confidence,
                "entry_price": r.entry_price,
                "invalidation_price": r.invalidation_price,
                "target_price": r.target_price,
                "component_scores": scores,
                "predicted_at": r.predicted_at.isoformat() if r.predicted_at else None,
                "feedback_due_at": feedback_due.isoformat() if feedback_due else None,
                "feedback_required": False,
                "can_record_trade_entry": can_record_entry,
                "can_record_outcome": can_record_outcome,
                "user_trade_entry": trade_entry,
                "evaluate_at": r.evaluate_at.isoformat() if r.evaluate_at else None,
                "actual_price": r.actual_price,
                "actual_direction": r.actual_direction,
                "was_correct": r.was_correct,
                "status": r.status,
                "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
                "user_feedback": outcome,
                "user_comment": uf.comment if uf else None,
                "market_outcome": mv.outcome if mv else None,
                "market_verification": {
                    "mfe": mv.max_favorable_excursion,
                    "mae": mv.max_adverse_excursion,
                    "invalidation_hit": mv.invalidation_hit,
                } if mv else None,
                "user_truthful": (not tr.conflict) if tr and uf and mv else None,
                "conflict": conflict,
                "training_ready": bool(tr and tr.admin_status == "APPROVED" and not tr.conflict),
            })
            if len(out) >= limit:
                break
        return out
    finally:
        db.close()


def bulk_retrain_reviews(
    *,
    review_ids: list[int] | None = None,
    use_all: bool = False,
    status: str | None = "evaluated",
    symbol: str | None = None,
    conflicts_only: bool = False,
    correct_only: bool = False,
    promote: bool = True,
) -> dict:
    """Retrain once per symbol for selected reviews, then mark them done."""
    from engine.data import get_data
    from engine.model_trainer import retrain_with_feedback
    from utils.config import INTERVAL

    if use_all:
        reviews_data = list_reviews(
            status=status,
            symbol=symbol,
            conflicts_only=conflicts_only,
            correct_only=correct_only,
            limit=500,
        )
        ids = [r["id"] for r in reviews_data]
    elif review_ids:
        ids = list(review_ids)
    else:
        return {"error": "Provide review_ids or use_all=true"}

    if not ids:
        return {"error": "No reviews matched your filters"}

    db = SessionLocal()
    try:
        rows = db.query(PredictionReview).filter(PredictionReview.id.in_(ids)).all()
        row_by_id = {r.id: r for r in rows}
    finally:
        db.close()

    by_symbol: dict[str, list[int]] = {}
    for rid in ids:
        row = row_by_id.get(rid)
        if not row:
            continue
        sym = row.symbol.upper()
        by_symbol.setdefault(sym, []).append(rid)

    symbol_results = []
    errors = []
    for sym, sym_ids in by_symbol.items():
        interval = DEFAULT_INTERVAL
        for rid in sym_ids:
            row = row_by_id.get(rid)
            if row and row.interval:
                interval = row.interval
                break
        try:
            df, source = get_data(sym, interval or INTERVAL, fetch=True)
            result = retrain_with_feedback(sym, df, interval or INTERVAL, promote=promote)
            if result is None:
                errors.append(f"{sym}: not enough data")
                continue
            for rid in sym_ids:
                set_review_status(rid, "retrain_done")
            symbol_results.append({
                "symbol": sym,
                "review_ids": sym_ids,
                "count": len(sym_ids),
                "promoted": result.get("promoted", False),
                "metrics": result.get("metrics"),
                "data_source": source,
            })
        except Exception as exc:
            log.exception("Bulk retrain failed for %s", sym)
            errors.append(f"{sym}: {exc}")

    if not symbol_results:
        return {"error": "; ".join(errors) or "Retrain failed"}

    return {
        "message": f"Retrained {len(symbol_results)} symbol(s) from {len(ids)} review(s)",
        "reviews_processed": len(ids),
        "symbols": symbol_results,
        "errors": errors,
    }


def set_review_status(review_id: int, status: str) -> bool:
    db = SessionLocal()
    try:
        row = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        if not row:
            return False
        row.status = status
        db.commit()
        return True
    finally:
        db.close()


def get_review(review_id: int) -> PredictionReview | None:
    db = SessionLocal()
    try:
        return db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
    finally:
        db.close()
