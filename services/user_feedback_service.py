# services/user_feedback_service.py
"""User-submitted feedback on predictions (required 2h after prediction)."""
from __future__ import annotations

import json
from datetime import datetime

from db.models import PredictionReview, UserFeedback
from db.session import SessionLocal
from services.prediction_review import verify_single_review
from services.training_service import reconcile_training_record
from utils.logger import get_logger

log = get_logger("services.user_feedback")

ALLOWED_FEEDBACK = frozenset({"SUCCESSFUL", "FAILED", "DID_NOT_TAKE", "UNCLEAR"})


def submit_feedback(
    user_id: int,
    prediction_id: int,
    feedback: str,
    comment: str | None = None,
) -> tuple[bool, str, UserFeedback | None]:
    fb = (feedback or "").strip().upper()
    if fb not in ALLOWED_FEEDBACK:
        return False, f"feedback must be one of: {', '.join(sorted(ALLOWED_FEEDBACK))}", None

    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == prediction_id).first()
        if not review:
            return False, "Prediction not found", None
        if review.user_id != user_id:
            return False, "Not your prediction", None

        due_at = review.feedback_due_at or review.evaluate_at
        if due_at and due_at > datetime.utcnow():
            mins = int((due_at - datetime.utcnow()).total_seconds() // 60) + 1
            return False, f"Feedback opens in ~{mins} minutes (2h after your prediction)", None

        existing = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.prediction_id == prediction_id,
                UserFeedback.user_id == user_id,
            )
            .first()
        )
        if existing:
            return False, "Feedback already submitted for this prediction", None

        row = UserFeedback(
            prediction_id=prediction_id,
            user_id=user_id,
            feedback=fb,
            comment=(comment or "").strip() or None,
            submitted_at=datetime.utcnow(),
        )
        db.add(row)
        if review.status == "pending":
            review.status = "awaiting_feedback"
        db.commit()
        db.refresh(row)

        verify_single_review(prediction_id)

        features = json.loads(review.features_json) if review.features_json else {}
        record = reconcile_training_record(
            prediction_id,
            features=features,
            predicted_action=review.predicted_action,
        )
        msg = "Feedback recorded"
        if record and record.conflict:
            msg = "Feedback recorded — your report differs from market data (flagged for admin review)"

        from db.models import User, MarketVerification
        from services.notification_service import notify_feedback_submitted
        user = db.query(User).filter(User.id == user_id).first()
        mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == prediction_id).first()
        notify_feedback_submitted(
            username=user.username if user else f"user#{user_id}",
            user_id=user_id,
            prediction_id=prediction_id,
            symbol=review.symbol,
            predicted_action=review.predicted_action,
            user_feedback=fb,
            market_direction=mv.actual_direction if mv else None,
            market_outcome=mv.outcome if mv else None,
            conflict=bool(record and record.conflict),
        )
        return True, msg, row
    except Exception:
        log.exception("submit_feedback failed")
        db.rollback()
        return False, "Failed to save feedback", None
    finally:
        db.close()
