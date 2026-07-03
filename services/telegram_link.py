# services/telegram_link.py
"""Telegram account linking via one-time codes."""
from datetime import datetime, timedelta

from db.models import TelegramLink, TelegramLinkCode, User
from db.session import SessionLocal
from utils.logger import get_logger
from utils.security import hash_password, check_password
import secrets

log = get_logger("services.telegram_link")

CODE_TTL_MINUTES = 15


def _bind_chat_to_user(db, user_id: int, chat_id: str) -> None:
    """Attach chat_id to user_id, replacing any prior link for that chat or user."""
    chat_id = str(chat_id)
    prior_user_ids = [
        row.user_id
        for row in db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).all()
        if row.user_id != user_id
    ]
    db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).delete(synchronize_session=False)
    db.query(TelegramLink).filter(
        TelegramLink.user_id == user_id,
        TelegramLink.chat_id != chat_id,
    ).delete(synchronize_session=False)

    existing = db.query(TelegramLink).filter(TelegramLink.user_id == user_id).first()
    if existing:
        existing.chat_id = chat_id
    else:
        db.add(TelegramLink(user_id=user_id, chat_id=chat_id))

    for orphan_id in prior_user_ids:
        orphan = db.query(User).filter(User.id == orphan_id).first()
        if orphan and str(orphan.email).endswith("@telegram.local"):
            remaining = db.query(TelegramLink).filter(TelegramLink.user_id == orphan_id).count()
            if remaining == 0:
                db.delete(orphan)
                log.info("Removed orphan Telegram-only user %s after link merge", orphan_id)


def create_link_code(user_id: int) -> str:
    """Generate a 6-digit link code for the user (replaces any prior code)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    db = SessionLocal()
    try:
        db.query(TelegramLinkCode).filter(TelegramLinkCode.user_id == user_id).delete()
        db.add(TelegramLinkCode(
            user_id=user_id,
            code_hash=hash_password(code),
            expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
        ))
        db.commit()
        return code
    finally:
        db.close()


def link_chat(user_id: int, chat_id: str, code: str) -> dict:
    """Bind chat_id to user after verifying the link code."""
    db = SessionLocal()
    try:
        row = (
            db.query(TelegramLinkCode)
            .filter(TelegramLinkCode.user_id == user_id, TelegramLinkCode.used.is_(False))
            .order_by(TelegramLinkCode.created_at.desc())
            .first()
        )
        if not row or row.expires_at < datetime.utcnow():
            return {"error": "Link code expired or not found"}
        row.attempts = (row.attempts or 0) + 1
        if row.attempts > 5:
            row.used = True
            db.commit()
            return {"error": "Too many attempts"}
        if not check_password(code, row.code_hash):
            db.commit()
            return {"error": "Invalid link code"}
        row.used = True
        _bind_chat_to_user(db, user_id, chat_id)
        db.commit()
        return {"success": True, "chat_id": str(chat_id)}
    except Exception as exc:
        db.rollback()
        log.exception("link_chat failed for user %s chat %s", user_id, chat_id)
        return {"error": str(exc)}
    finally:
        db.close()


def redeem_link_code(chat_id: str, code: str) -> dict:
    """Bind chat_id using a one-time link code (from /telegram/link-code)."""
    code = (code or "").strip()
    if not code:
        return {"error": "Link code required"}
    db = SessionLocal()
    try:
        rows = (
            db.query(TelegramLinkCode)
            .filter(
                TelegramLinkCode.used.is_(False),
                TelegramLinkCode.expires_at > datetime.utcnow(),
            )
            .order_by(TelegramLinkCode.id.desc())
            .all()
        )
        for row in rows:
            if not check_password(code, row.code_hash):
                continue
            row.used = True
            _bind_chat_to_user(db, row.user_id, chat_id)
            db.commit()
            log.info("Telegram chat %s linked to user %s", chat_id, row.user_id)
            return {"success": True, "user_id": row.user_id}
        return {"error": "Invalid or expired link code"}
    except Exception as exc:
        db.rollback()
        log.exception("redeem_link_code failed for chat %s", chat_id)
        return {"error": str(exc)}
    finally:
        db.close()


def unlink_user(user_id: int) -> dict:
    db = SessionLocal()
    try:
        deleted = db.query(TelegramLink).filter(TelegramLink.user_id == user_id).delete()
        db.commit()
        return {"success": bool(deleted)}
    finally:
        db.close()


def get_chat_id(user_id: int) -> str | None:
    db = SessionLocal()
    try:
        link = db.query(TelegramLink).filter(TelegramLink.user_id == user_id).first()
        return link.chat_id if link else None
    finally:
        db.close()


def get_user_by_chat(chat_id: str) -> User | None:
    db = SessionLocal()
    try:
        link = db.query(TelegramLink).filter(TelegramLink.chat_id == str(chat_id)).first()
        if not link:
            return None
        return db.query(User).filter(User.id == link.user_id).first()
    finally:
        db.close()


def get_or_register_telegram_user(
    chat_id: str,
    telegram_username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Return linked user, creating a pending account on first /start if needed."""
    user = get_user_by_chat(chat_id)
    if user:
        return user
    from services.user_service import register_telegram_user
    return register_telegram_user(chat_id, telegram_username, first_name)
