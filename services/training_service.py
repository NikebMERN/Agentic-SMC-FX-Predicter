# services/training_service.py
"""Training records from verified predictions + user feedback reconciliation."""
from __future__ import annotations

import json
from datetime import datetime

from db.models import MarketVerification, PredictionReview, TrainingRecord, User, UserFeedback
from db.session import SessionLocal
from engine.confluence import ACTION_BUY, ACTION_NO_TRADE, ACTION_SELL, ACTION_WAIT
from services.notifier import notify_admin
from utils.logger import get_logger

log = get_logger("services.training_service")

FEEDBACK_LABEL_MAP = {
    "SUCCESSFUL": "correct",
    "FAILED": "wrong",
    "DID_NOT_TAKE": "skipped",
    "UNCLEAR": "unclear",
}

MARKET_LABEL_MAP = {
    "UP": "up",
    "DOWN": "down",
    "SIDEWAYS": "flat",
}

BULLISH = frozenset({ACTION_BUY, "BUY", "BUY_BIAS"})
BEARISH = frozenset({ACTION_SELL, "SELL", "SELL_BIAS"})
NON_TRADE = frozenset({ACTION_NO_TRADE, ACTION_WAIT, "NO_TRADE", "WAIT_FOR_CONFIRMATION"})


def _market_favored_prediction(predicted_action: str, actual_direction: str | None) -> bool | None:
    if not actual_direction:
        return None
    if predicted_action in BULLISH:
        return actual_direction == "UP"
    if predicted_action in BEARISH:
        return actual_direction == "DOWN"
    if predicted_action in NON_TRADE:
        return actual_direction == "SIDEWAYS"
    return None


def detect_conflict(
    user_feedback: str | None,
    actual_direction: str | None,
    predicted_action: str,
) -> bool:
    """True when user feedback disagrees with measured market direction."""
    if not user_feedback or user_feedback in ("DID_NOT_TAKE", "UNCLEAR"):
        return False
    favored = _market_favored_prediction(predicted_action, actual_direction)
    if favored is None:
        return False
    if user_feedback == "SUCCESSFUL":
        return not favored
    if user_feedback == "FAILED":
        return favored
    return False


def reconcile_training_record(
    prediction_id: int,
    *,
    features: dict | None = None,
    predicted_action: str | None = None,
) -> TrainingRecord | None:
    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == prediction_id).first()
        uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == prediction_id).first()
        mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == prediction_id).first()
        row = db.query(TrainingRecord).filter(TrainingRecord.prediction_id == prediction_id).first()
        action = predicted_action or (review.predicted_action if review else "")

        label_market = MARKET_LABEL_MAP.get(mv.actual_direction) if mv and mv.actual_direction else None
        label_user = FEEDBACK_LABEL_MAP.get(uf.feedback) if uf else None
        conflict = detect_conflict(
            uf.feedback if uf else None,
            mv.actual_direction if mv else None,
            action,
        )
        final_label = label_market or ("flat" if action in NON_TRADE else None)

        if not row:
            row = TrainingRecord(prediction_id=prediction_id)
            db.add(row)

        was_conflict = row.conflict
        row.user_feedback_id = uf.id if uf else row.user_feedback_id
        row.market_verification_id = mv.id if mv else row.market_verification_id
        if features:
            row.features_json = json.dumps(features)
        row.label_from_market = label_market
        row.label_from_user = label_user
        row.final_label = final_label
        row.conflict = conflict
        db.commit()
        db.refresh(row)

        if conflict and not was_conflict and review and review.user_id:
            user = db.query(User).filter(User.id == review.user_id).first()
            username = user.username if user else f"user#{review.user_id}"
            notify_admin(
                f"Feedback conflict: {username} reported {uf.feedback if uf else '?'} on "
                f"{review.symbol} {review.predicted_action}, but market moved {mv.actual_direction if mv else '?'}."
            )
            log.warning(
                "Feedback conflict for user %s review %s: user=%s market=%s",
                username, prediction_id, uf.feedback if uf else None, mv.actual_direction if mv else None,
            )
        return row
    except Exception:
        log.exception("Failed to reconcile training record for prediction %s", prediction_id)
        db.rollback()
        return None
    finally:
        db.close()


def list_training_records(status: str | None = None, limit: int = 100) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(TrainingRecord).order_by(TrainingRecord.id.desc())
        if status:
            q = q.filter(TrainingRecord.admin_status == status.upper())
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            review = db.query(PredictionReview).filter(PredictionReview.id == r.prediction_id).first()
            user = None
            if review and review.user_id:
                user = db.query(User).filter(User.id == review.user_id).first()
            uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == r.prediction_id).first()
            mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == r.prediction_id).first()
            out.append({
                "id": r.id,
                "prediction_id": r.prediction_id,
                "user_id": review.user_id if review else None,
                "username": user.username if user else None,
                "symbol": review.symbol if review else None,
                "predicted_action": review.predicted_action if review else None,
                "user_feedback": uf.feedback if uf else None,
                "market_direction": mv.actual_direction if mv else None,
                "market_outcome": mv.outcome if mv else None,
                "label_from_market": r.label_from_market,
                "label_from_user": r.label_from_user,
                "final_label": r.final_label,
                "conflict": r.conflict,
                "user_truthful": not r.conflict if uf and mv else None,
                "label_quality_score": r.label_quality_score,
                "admin_status": r.admin_status,
                "admin_notes": r.admin_notes,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return out
    finally:
        db.close()


def review_training_record(
    record_id: int,
    admin_status: str,
    admin_notes: str | None = None,
    label_quality_score: float | None = None,
) -> TrainingRecord | None:
    db = SessionLocal()
    try:
        row = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
        if not row:
            return None
        row.admin_status = admin_status.upper()
        row.admin_notes = admin_notes
        if label_quality_score is not None:
            row.label_quality_score = label_quality_score
        row.reviewed_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def export_approved_records(limit: int = 5000) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(TrainingRecord)
            .filter(TrainingRecord.admin_status == "APPROVED")
            .order_by(TrainingRecord.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "prediction_id": r.prediction_id,
                "features": json.loads(r.features_json) if r.features_json else {},
                "final_label": r.final_label,
                "label_quality_score": r.label_quality_score,
            }
            for r in rows
        ]
    finally:
        db.close()
