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
from services.training_service import reconcile_training_record
from services.user_access import FEEDBACK_DUE_HOURS
from utils import settings
from utils.logger import get_logger

log = get_logger("services.prediction_review")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "snapshots")
MAX_VERIFY_RETRIES = int(os.getenv("PREDICTION_VERIFY_MAX_RETRIES", "5"))

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


def _atr_fraction_threshold(entry: float, atr: float) -> float:
    frac = settings.get_float("verification_atr_fraction", 0.25)
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
) -> dict:
    """Candle-based MFE/MAE with invalidation-first logic."""
    if candles.empty or entry <= 0:
        raise ValueError("Insufficient candle data for verification")

    threshold = _atr_fraction_threshold(entry, atr)
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
    snapshot_df: pd.DataFrame | None = None,
    snapshot_records: list[dict] | None = None,
    source: str = "web",
) -> PredictionReview | None:
    db = SessionLocal()
    try:
        horizon_key, _hours = parse_horizon(horizon)
        now = datetime.utcnow()
        due = now + timedelta(hours=FEEDBACK_DUE_HOURS)
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
            predicted_at=now,
            feedback_due_at=due,
            feedback_reminder_sent=False,
            evaluate_at=due,
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
            df, _ = get_data(row.symbol, row.interval, fetch=True)
            predicted_at = row.predicted_at or datetime.utcnow()
            window = df[df.index >= pd.Timestamp(predicted_at)]
            if window.empty:
                window = df.tail(max(10, FEEDBACK_DUE_HOURS * 4))
            atr = float((window["High"] - window["Low"]).mean()) if len(window) else 0.001
            result = verify_candles(
                window,
                entry=row.entry_price or float(window["Close"].iloc[0]),
                invalidation=row.invalidation_price,
                target=row.target_price,
                predicted_action=row.predicted_action,
                atr=atr,
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
) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(PredictionReview).order_by(PredictionReview.id.desc())
        if status:
            q = q.filter(PredictionReview.status == status)
        if user_id is not None:
            q = q.filter(PredictionReview.user_id == user_id)
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            scores = json.loads(r.scores_json) if r.scores_json else {}
            uf = r.user_feedback
            mv = r.market_verification
            now = datetime.utcnow()
            feedback_due = r.feedback_due_at or r.evaluate_at
            feedback_open = feedback_due and feedback_due <= now and not uf
            tr = r.training_record
            out.append({
                "id": r.id,
                "signal_id": r.signal_id,
                "user_id": r.user_id,
                "symbol": r.symbol,
                "interval": r.interval,
                "horizon": r.horizon,
                "predicted_action": r.predicted_action,
                "direction": r.direction,
                "predicted_confidence": r.predicted_confidence,
                "entry_price": r.entry_price,
                "invalidation_price": r.invalidation_price,
                "target_price": r.target_price,
                "component_scores": scores,
                "predicted_at": r.predicted_at.isoformat() if r.predicted_at else None,
                "feedback_due_at": feedback_due.isoformat() if feedback_due else None,
                "feedback_required": bool(feedback_open),
                "evaluate_at": r.evaluate_at.isoformat() if r.evaluate_at else None,
                "actual_price": r.actual_price,
                "actual_direction": r.actual_direction,
                "was_correct": r.was_correct,
                "status": r.status,
                "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
                "user_feedback": uf.feedback if uf else None,
                "user_comment": uf.comment if uf else None,
                "market_outcome": mv.outcome if mv else None,
                "market_verification": {
                    "mfe": mv.max_favorable_excursion,
                    "mae": mv.max_adverse_excursion,
                    "invalidation_hit": mv.invalidation_hit,
                } if mv else None,
                "user_truthful": (not tr.conflict) if tr and uf and mv else None,
                "conflict": tr.conflict if tr else False,
            })
        return out
    finally:
        db.close()


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
