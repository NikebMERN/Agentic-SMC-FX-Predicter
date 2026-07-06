"""TP/SL outcome verification for meta-label training."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from db.models import PredictionReview, SignalOutcome
from db.session import SessionLocal
from engine.confluence import ACTION_BUY, ACTION_SELL
from engine.data import get_data
from ml.labels import OUTCOME_EXPIRED, evaluate_tp_sl_path, outcome_to_meta_label
from services.prediction_review import parse_horizon
from utils.logger import get_logger

log = get_logger("services.signal_outcome")

TRADE_ACTIONS = frozenset({ACTION_BUY, ACTION_SELL, "BUY", "SELL", "BUY_BIAS", "SELL_BIAS"})


def _direction_from_review(row: PredictionReview) -> str | None:
    action = (row.predicted_action or "").upper()
    if row.direction:
        return row.direction
    if action in ("BUY", "BUY_BIAS"):
        return "bullish"
    if action in ("SELL", "SELL_BIAS"):
        return "bearish"
    return None


def verify_prediction_outcome(review_id: int) -> SignalOutcome | None:
    db = SessionLocal()
    try:
        row = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        if not row or row.predicted_action.upper() not in TRADE_ACTIONS:
            return None
        existing = db.query(SignalOutcome).filter(SignalOutcome.prediction_id == review_id).first()
        if existing:
            return existing
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        if not row:
            return None

        direction = _direction_from_review(row)
        if not direction:
            return None

        _, horizon_hours = parse_horizon(row.horizon or "intraday")
        predicted_at = row.predicted_at or datetime.utcnow()
        horizon_end = predicted_at + timedelta(hours=horizon_hours)

        df, _ = get_data(row.symbol, row.interval, fetch=True)
        if df.empty:
            return None

        window = df[(df.index >= pd.Timestamp(predicted_at)) & (df.index <= pd.Timestamp(horizon_end))]
        if window.empty:
            window = df[df.index >= pd.Timestamp(predicted_at)]

        entry = float(row.entry_price or 0)
        tp = row.target_price
        sl = row.invalidation_price
        outcome, mfe, mae = evaluate_tp_sl_path(
            window,
            direction=direction,
            entry=entry,
            tp=float(tp) if tp else None,
            sl=float(sl) if sl else None,
        )

        meta_label = outcome_to_meta_label(outcome)
        so = SignalOutcome(
            prediction_id=row.id,
            rule_direction=direction,
            tp_price=tp,
            sl_price=sl,
            entry_price=entry,
            outcome=outcome if outcome != OUTCOME_EXPIRED else "EXPIRED",
            max_favorable_excursion=mfe,
            max_adverse_excursion=mae,
            meta_label=meta_label,
            verified_at=datetime.utcnow(),
        )
        db.add(so)
        db.commit()
        db.refresh(so)
        log.info("SignalOutcome %s for review %s: %s", so.id, review_id, so.outcome)
        return so
    except Exception:
        log.exception("Signal outcome verification failed for review %s", review_id)
        db.rollback()
        return None
    finally:
        db.close()


def verify_due_outcomes(limit: int = 50) -> int:
    """Verify predictions past horizon that lack SignalOutcome."""
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        rows = (
            db.query(PredictionReview)
            .outerjoin(SignalOutcome, SignalOutcome.prediction_id == PredictionReview.id)
            .filter(
                SignalOutcome.id.is_(None),
                PredictionReview.predicted_action.in_(list(TRADE_ACTIONS)),
                PredictionReview.evaluate_at <= now,
            )
            .limit(limit)
            .all()
        )
        ids = [r.id for r in rows]
    finally:
        db.close()

    count = 0
    for rid in ids:
        if verify_prediction_outcome(rid):
            count += 1
    return count
