# services/feedback_reminder.py
"""Optional nudge for users to record whether they entered a trade signal."""
from datetime import datetime

from db.models import PredictionReview, User
from db.session import SessionLocal
from services.notifier import notify_user
from services.prediction_review import is_trade_signal
from utils.compliance import assert_safe_wording, DISCLAIMER
from utils.logger import get_logger

log = get_logger("services.feedback_reminder")


def _feedback_message(review: PredictionReview, user: User | None) -> str:
    name = user.username if user else "trader"
    return assert_safe_wording(
        f"Hi {name}, optional check-in for your {review.symbol} signal "
        f"({review.predicted_action} @ {review.entry_price}).\n"
        f"Did you enter this trade? Reply on the web app or use:\n"
        f"/feedback {review.id} SUCCESSFUL|FAILED|DID_NOT_TAKE\n\n"
        f"{DISCLAIMER}"
    )


def send_due_feedback_reminders() -> int:
    """Notify users about optional trade-entry recording. Returns count sent."""
    db = SessionLocal()
    try:
        due = (
            db.query(PredictionReview)
            .filter(
                PredictionReview.feedback_due_at <= datetime.utcnow(),
                PredictionReview.feedback_reminder_sent.is_(False),
                PredictionReview.user_id.isnot(None),
            )
            .all()
        )
    finally:
        db.close()

    sent = 0
    for review in due:
        if not is_trade_signal(review.predicted_action):
            db = SessionLocal()
            try:
                row = db.query(PredictionReview).filter(PredictionReview.id == review.id).first()
                if row:
                    row.feedback_reminder_sent = True
                    db.commit()
            finally:
                db.close()
            continue

        db = SessionLocal()
        try:
            row = db.query(PredictionReview).filter(PredictionReview.id == review.id).first()
            if not row or row.feedback_reminder_sent:
                continue
            if row.user_feedback:
                from services.feedback_fields import split_feedback_fields
                te, oc = split_feedback_fields(row.user_feedback)
                if oc or te == "DID_NOT_TAKE":
                    row.feedback_reminder_sent = True
                    db.commit()
                    continue

            user = db.query(User).filter(User.id == row.user_id).first()
            msg = _feedback_message(row, user)
            if row.user_id:
                from services.notification_service import notify_feedback_due
                notify_feedback_due(
                    row.user_id,
                    prediction_id=row.id,
                    symbol=row.symbol,
                    predicted_action=row.predicted_action,
                )
            if row.user_id and notify_user(row.user_id, msg):
                sent += 1
            row.feedback_reminder_sent = True
            db.commit()
            log.info("Trade-entry reminder sent for review %s (user %s)", row.id, row.user_id)
        finally:
            db.close()

    return sent
