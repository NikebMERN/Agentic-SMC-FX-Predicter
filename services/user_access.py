# services/user_access.py
"""User approval status and prediction access checks."""
import os

from db.models import User
from db.session import SessionLocal

DEFAULT_SIGNALS_QUOTA = int(os.getenv("DEFAULT_SIGNALS_QUOTA", "5"))
FEEDBACK_DUE_HOURS = int(os.getenv("FEEDBACK_DUE_HOURS", "2"))


def get_user(user_id: int) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def user_status(user: User) -> str:
    status = getattr(user, "status", None)
    if status:
        return status
    return "active" if user.is_active else "pending"


def can_use_predictions(user: User | None) -> tuple[bool, str]:
    if not user:
        return False, "User not found"
    status = user_status(user)
    if status == "pending":
        return False, "Account pending admin approval — predictions are disabled until approved."
    if status == "banned" or not user.is_active:
        return False, "Account is suspended — contact support."
    if user.signals_remaining <= 0:
        return False, f"Free trial quota exhausted ({DEFAULT_SIGNALS_QUOTA} predictions total across web and Telegram). Contact admin to top up."
    return True, ""


def decrement_quota(user_id: int) -> tuple[bool, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        ok, msg = can_use_predictions(user)
        if not ok:
            return False, msg
        user.signals_remaining -= 1
        db.commit()
        return True, f"Quota remaining: {user.signals_remaining}"
    finally:
        db.close()


def increment_quota(user_id: int, amount: int = 1) -> None:
    """Refund prediction quota (e.g. after a failed analyze/predict)."""
    if amount <= 0:
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.signals_remaining += amount
            db.commit()
    finally:
        db.close()
