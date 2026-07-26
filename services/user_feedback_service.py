# services/user_feedback_service.py
"""User feedback: trade entry (predict page) and outcome (feedback page)."""
from __future__ import annotations

import json
from datetime import datetime

from db.models import PredictionReview, UserFeedback
from db.session import SessionLocal
from services.feedback_fields import (
    ALLOWED_FEEDBACK,
    OUTCOME_VALUES,
    TRADE_ENTRY_VALUES,
    split_feedback_fields,
)
from services.prediction_review import is_trade_signal
from utils.logger import get_logger

log = get_logger("services.user_feedback")

def submit_feedback(
    user_id: int,
    prediction_id: int,
    feedback: str,
    comment: str | None = None,
    *,
    kind: str | None = None,
    screenshot_path: str | None = None,
    account_type: str | None = None,
    execution_delay_ms: int | None = None,
    manual_notes: str | None = None,
) -> tuple[bool, str, UserFeedback | None]:
    fb = (feedback or "").strip().upper()
    if fb not in ALLOWED_FEEDBACK:
        return False, f"feedback must be one of: {', '.join(sorted(ALLOWED_FEEDBACK))}", None

    if kind is None:
        kind = "trade_entry" if fb in TRADE_ENTRY_VALUES else "outcome"
    if kind not in ("trade_entry", "outcome"):
        return False, "kind must be 'trade_entry' or 'outcome'", None
    if kind == "trade_entry" and fb not in TRADE_ENTRY_VALUES:
        return False, f"trade entry must be one of: {', '.join(sorted(TRADE_ENTRY_VALUES))}", None
    if kind == "outcome" and fb not in OUTCOME_VALUES:
        return False, f"outcome must be one of: {', '.join(sorted(OUTCOME_VALUES))}", None

    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == prediction_id).first()
        if not review:
            return False, "Prediction not found", None
        if review.user_id != user_id:
            return False, "Not your prediction", None
        if not is_trade_signal(review.predicted_action):
            return False, "Feedback is not collected for NO_TRADE or WAIT_FOR_CONFIRMATION signals", None

        existing = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.prediction_id == prediction_id,
                UserFeedback.user_id == user_id,
            )
            .first()
        )
        trade_entry, outcome = split_feedback_fields(existing)

        if kind == "trade_entry":
            if trade_entry:
                return False, "Trade entry already recorded for this prediction", None
            if existing:
                existing.trade_entry = fb
                if comment:
                    existing.comment = (comment or "").strip() or existing.comment
            else:
                row = UserFeedback(
                    prediction_id=prediction_id,
                    user_id=user_id,
                    trade_entry=fb,
                    feedback=None,
                    comment=(comment or "").strip() or None,
                    submitted_at=datetime.utcnow(),
                )
                db.add(row)
                existing = row
        else:
            if outcome:
                return False, "Outcome already recorded for this prediction", None
            if existing:
                existing.feedback = fb
                if comment:
                    existing.comment = (comment or "").strip() or existing.comment
            else:
                row = UserFeedback(
                    prediction_id=prediction_id,
                    user_id=user_id,
                    trade_entry=None,
                    feedback=fb,
                    comment=(comment or "").strip() or None,
                    submitted_at=datetime.utcnow(),
                )
                db.add(row)
                existing = row

        existing.screenshot_path = screenshot_path or existing.screenshot_path
        existing.account_type = account_type or existing.account_type
        if execution_delay_ms is not None:
            existing.execution_delay_ms = max(0, int(execution_delay_ms))
        existing.manual_notes = manual_notes or existing.manual_notes
        if review.status == "pending":
            review.status = "awaiting_feedback"
        db.commit()
        db.refresh(existing)

        from services.prediction_review import verify_single_review
        verify_single_review(prediction_id)

        from services.training_service import reconcile_training_record
        features = json.loads(review.features_json) if review.features_json else {}
        record = reconcile_training_record(
            prediction_id,
            features=features,
            predicted_action=review.predicted_action,
        )
        msg = "Trade entry recorded" if kind == "trade_entry" else "Outcome recorded"
        if record and record.conflict:
            msg = f"{msg} — your report differs from market data (flagged for admin review)"

        from db.models import User, MarketVerification
        from services.notification_service import notify_feedback_submitted
        user = db.query(User).filter(User.id == user_id).first()
        mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == prediction_id).first()
        te, oc = split_feedback_fields(existing)
        notify_feedback_submitted(
            username=user.username if user else f"user#{user_id}",
            user_id=user_id,
            prediction_id=prediction_id,
            symbol=review.symbol,
            predicted_action=review.predicted_action,
            user_feedback=oc or te or fb,
            market_direction=mv.actual_direction if mv else None,
            market_outcome=mv.outcome if mv else None,
            conflict=bool(record and record.conflict),
        )
        return True, msg, existing
    except Exception:
        log.exception("submit_feedback failed")
        db.rollback()
        return False, "Failed to save feedback", None
    finally:
        db.close()
