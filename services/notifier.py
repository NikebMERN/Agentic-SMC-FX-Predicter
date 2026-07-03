# services/notifier.py
"""Send Telegram notifications to linked admin/users."""
import time

import requests

from services.telegram_link import get_chat_id
from services.user_access import decrement_quota
from utils.config import TELEGRAM_BOT_TOKEN
from utils.config import ADMIN_EMAIL
from db.models import TelegramLink, User
from db.session import SessionLocal
from utils.logger import get_logger
from utils import settings

log = get_logger("services.notifier")


def send_message(chat_id: str, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        return False
    from utils.compliance import assert_safe_wording, DISCLAIMER
    safe = assert_safe_wording(text)
    if DISCLAIMER not in safe:
        safe = f"{safe}\n\n{DISCLAIMER}"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": safe[:4096]},
            timeout=15,
        )
        return r.ok
    except Exception as exc:
        log.warning("Telegram send failed: %s", exc)
        return False


def notify_user(user_id: int, text: str) -> bool:
    chat_id = get_chat_id(user_id)
    if not chat_id:
        return False
    return send_message(chat_id, text)


def notify_admin(text: str) -> bool:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL, User.role == "admin").first()
        if user:
            return notify_user(user.id, text)
    finally:
        db.close()
    return False


def broadcast_signal(signal, text: str) -> int:
    """Push a signal to linked, approved users with quota. Returns send count."""
    if not settings.get_broadcast_signals():
        return 0
    if not TELEGRAM_BOT_TOKEN:
        return 0

    db = SessionLocal()
    try:
        rows = (
            db.query(User, TelegramLink)
            .join(TelegramLink, TelegramLink.user_id == User.id)
            .filter(
                User.status == "active",
                User.is_active.is_(True),
                User.signals_remaining > 0,
            )
            .all()
        )
    finally:
        db.close()

    sent = 0
    for user, link in rows:
        ok, _ = decrement_quota(user.id)
        if not ok:
            continue
        if send_message(link.chat_id, text):
            sent += 1
        time.sleep(0.05)

    if sent:
        log.info("Broadcast signal %s to %s Telegram user(s)", getattr(signal, "id", "?"), sent)
    return sent
