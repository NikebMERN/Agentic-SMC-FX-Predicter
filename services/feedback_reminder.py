# services/feedback_reminder.py
"""Prompt users for trade feedback 2 hours after a prediction (web + Telegram)."""
from datetime import datetime

from db.models import PredictionReview, User
from db.session import SessionLocal
from services.notifier import notify_user
from utils.compliance import assert_safe_wording, DISCLAIMER
from utils.logger import get_logger

log = get_logger("services.feedback_reminder")


def _feedback_message(review: PredictionReview, user: User | None) -> str:
    name = user.username if user else "trader"
    return assert_safe_wording(
        f"Hi {name}, please rate your {review.symbol} prediction "
        f"({review.predicted_action} @ {review.entry_price}).\n"
        f"Reply on the web Feedback page or use:\n"
        f"/feedback {review.id} SUCCESSFUL|FAILED|DID_NOT_TAKE\n\n"
        f"{DISCLAIMER}"
    )


def send_due_feedback_reminders() -> int:
    """Notify users whose 2h feedback window is open. Returns count sent."""
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
        db = SessionLocal()
        try:
            row = db.query(PredictionReview).filter(PredictionReview.id == review.id).first()
            if not row or row.feedback_reminder_sent:
                continue
            if row.user_feedback:
                row.feedback_reminder_sent = True
                db.commit()
                continue

            user = db.query(User).filter(User.id == row.user_id).first()
            msg = _feedback_message(row, user)
            if row.user_id and notify_user(row.user_id, msg):
                sent += 1
            row.feedback_reminder_sent = True
            db.commit()
            log.info("Feedback reminder sent for review %s (user %s)", row.id, row.user_id)
        finally:
            db.close()

    return sent
