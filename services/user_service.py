# services/user_service.py
import secrets
from datetime import datetime, timedelta

from db.session import SessionLocal
from db.models import PasswordReset, User
from utils import mailer
from utils.logger import get_logger
from utils.security import hash_password, check_password, generate_token, generate_refresh_token
from services.user_access import DEFAULT_SIGNALS_QUOTA
from sqlalchemy.exc import IntegrityError # type: ignore
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

log = get_logger("user_service")

MIN_PASSWORD_LENGTH = 8
RESET_CODE_TTL_MINUTES = 15
RESET_MAX_ATTEMPTS = 5


def validate_password(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    return None

def register_user(username: str, email: str, password: str):
    db = SessionLocal()
    try:
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            status="active",
            is_active=True,
            signals_remaining=DEFAULT_SIGNALS_QUOTA,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        return None  # username/email already exists
    finally:
        db.close()

def login_user(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None, "invalid_credentials"
        if not check_password(password, user.password_hash):
            return None, "invalid_credentials"
        status = getattr(user, "status", "active" if user.is_active else "pending")
        if status == "banned" or (not user.is_active and status != "pending"):
            return None, "account_suspended"
        token = generate_token(user.id)
        refresh = generate_refresh_token(user.id)
        return {
            "user": user,
            "token": token,
            "refresh_token": refresh,
            "must_change_password": getattr(user, "must_change_password", False),
            "status": status,
        }, None
    finally:
        db.close()

def register_telegram_user(
    chat_id: str,
    telegram_username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Create a pending platform account for a Telegram user and link their chat."""
    import re
    from db.models import TelegramLink

    db = SessionLocal()
    email = f"tg_{chat_id}@telegram.local"
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            user = existing
        else:
            base = (telegram_username or first_name or f"tg_{chat_id}").strip()
            base = re.sub(r"[^\w]", "_", base)[:40] or f"tg_{chat_id}"
            username = base
            n = 0
            while db.query(User).filter(User.username == username).first():
                n += 1
                username = f"{base}_{n}"
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                status="active",
                is_active=True,
                signals_remaining=DEFAULT_SIGNALS_QUOTA,
            )
            db.add(user)
            db.flush()

        from services.telegram_link import _bind_chat_to_user
        _bind_chat_to_user(db, user.id, str(chat_id))
        db.commit()
        db.refresh(user)
        log.info("Telegram user registered: %s (chat %s)", user.username, chat_id)
        return user
    except IntegrityError:
        db.rollback()
        user = db.query(User).filter(User.email == email).first()
        if user:
            return user
        raise
    finally:
        db.close()

def approve_user(user_id: int, signals_remaining: int) -> User | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        user.status = "active"
        user.is_active = True
        user.signals_remaining = max(0, int(signals_remaining))
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

def get_user_by_id(user_id: int):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


# ---------------------------------------------------------------------
# Password reset (forgot password) and change
# ---------------------------------------------------------------------
def request_password_reset(email: str) -> dict:
    """Issue a one-time 6-digit code, store it hashed, email it.

    Returns {'user_exists', 'sent', 'code'}. The caller must never leak
    user_exists to the client; code is only for development mode when
    SMTP is not configured.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or getattr(user, "status", "active") != "active" or not user.is_active:
            return {"user_exists": False, "sent": False, "code": None}

        # One active code per user — invalidate older ones.
        db.query(PasswordReset).filter(
            PasswordReset.user_id == user.id, PasswordReset.used.is_(False)
        ).update({PasswordReset.used: True})

        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(PasswordReset(
            user_id=user.id,
            code_hash=hash_password(code),
            expires_at=datetime.utcnow() + timedelta(minutes=RESET_CODE_TTL_MINUTES),
        ))
        db.commit()

        sent = mailer.send_email(
            user.email,
            "SmartFlow AI - password reset code",
            f"Your password reset code is: {code}\n\n"
            f"It expires in {RESET_CODE_TTL_MINUTES} minutes. "
            "If you did not request this, ignore this email.",
        )
        log.info("Password reset requested for user %s (email sent: %s)", user.id, sent)
        return {"user_exists": True, "sent": sent, "code": code}
    finally:
        db.close()


def reset_password(email: str, code: str, new_password: str) -> tuple[bool, str]:
    """Verify the emailed code and set the new password."""
    error = validate_password(new_password)
    if error:
        return False, error

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False, "Invalid code"  # never reveal whether the email exists

        reset = (
            db.query(PasswordReset)
            .filter(
                PasswordReset.user_id == user.id,
                PasswordReset.used.is_(False),
                PasswordReset.expires_at > datetime.utcnow(),
            )
            .order_by(PasswordReset.id.desc())
            .first()
        )
        if not reset or reset.attempts >= RESET_MAX_ATTEMPTS:
            return False, "Code expired or too many attempts - request a new one"

        if not check_password(code or "", reset.code_hash):
            reset.attempts += 1
            db.commit()
            return False, "Invalid code"

        reset.used = True
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        db.commit()
        log.info("Password reset completed for user %s", user.id)
        return True, "Password updated - you can sign in now"
    finally:
        db.close()


def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    """Change password for a logged-in user (requires the current one)."""
    error = validate_password(new_password)
    if error:
        return False, error

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"
        if not check_password(current_password or "", user.password_hash):
            return False, "Current password is incorrect"
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        db.commit()
        log.info("Password changed for user %s", user_id)
        return True, "Password changed"
    finally:
        db.close()
