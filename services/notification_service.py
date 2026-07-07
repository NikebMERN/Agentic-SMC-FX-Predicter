# services/notification_service.py
"""In-app notifications for users and admins."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from db.models import Notification, User
from db.session import SessionLocal
from utils.logger import get_logger

log = get_logger("services.notification_service")

MAX_LIST = 50


def _serialize(row: Notification) -> dict:
    meta = None
    if row.meta_json:
        try:
            meta = json.loads(row.meta_json)
        except json.JSONDecodeError:
            meta = None
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "link": row.link,
        "meta": meta,
        "read": row.read,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_notification(
    user_id: int,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
    meta: dict | None = None,
) -> Notification | None:
    db = SessionLocal()
    try:
        row = Notification(
            user_id=user_id,
            kind=kind,
            title=title[:160],
            body=body,
            link=link,
            meta_json=json.dumps(meta) if meta else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        log.exception("create_notification failed for user %s kind %s", user_id, kind)
        db.rollback()
        return None
    finally:
        db.close()


def notify_admins(
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
    meta: dict | None = None,
) -> int:
    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.role == "admin").all()
    finally:
        db.close()
    count = 0
    for admin in admins:
        if create_notification(
            admin.id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            meta=meta,
        ):
            count += 1
    return count


def list_notifications(user_id: int, *, unread_only: bool = False, limit: int = MAX_LIST) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            q = q.filter(Notification.read.is_(False))
        rows = q.order_by(Notification.id.desc()).limit(min(limit, MAX_LIST)).all()
        return [_serialize(r) for r in rows]
    finally:
        db.close()


def unread_count(user_id: int) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read.is_(False))
            .count()
        )
    finally:
        db.close()


def mark_read(notification_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if not row:
            return False
        row.read = True
        db.commit()
        return True
    finally:
        db.close()


def mark_all_read(user_id: int) -> int:
    db = SessionLocal()
    try:
        updated = (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read.is_(False))
            .update({"read": True}, synchronize_session=False)
        )
        db.commit()
        return updated
    finally:
        db.close()


def notify_feedback_submitted(
    *,
    username: str,
    user_id: int,
    prediction_id: int,
    symbol: str,
    predicted_action: str,
    user_feedback: str,
    market_direction: str | None,
    market_outcome: str | None,
    conflict: bool,
) -> None:
    comparison = (
        f"Your report: {user_feedback} · Market: {market_direction or 'pending'}"
        f"{f' ({market_outcome})' if market_outcome else ''}"
    )
    if conflict:
        title = f"Feedback conflict — {username} · {symbol}"
        body = (
            f"{username} reported {user_feedback} on {symbol} {predicted_action}, "
            f"but market moved {market_direction or '?'}. {comparison}"
        )
        kind = "feedback_conflict"
        link = "/training-records"
    else:
        title = f"User feedback — {username} · {symbol}"
        body = f"{username} rated {symbol} {predicted_action} as {user_feedback}. {comparison}"
        kind = "feedback_submitted"
        link = "/reviews"
    notify_admins(
        kind=kind,
        title=title,
        body=body,
        link=link,
        meta={
            "user_id": user_id,
            "username": username,
            "prediction_id": prediction_id,
            "symbol": symbol,
            "predicted_action": predicted_action,
            "user_feedback": user_feedback,
            "market_direction": market_direction,
            "market_outcome": market_outcome,
            "conflict": conflict,
        },
    )


def notify_confirmation_ready(
    user_id: int,
    *,
    watch_id: int,
    symbol: str,
    confirmed_action: str,
    wait_reason: str,
    confirmation_reason: str,
) -> None:
    create_notification(
        user_id,
        kind="confirmation_ready",
        title=f"Ready to enter — {symbol} {confirmed_action}",
        body=(
            f"Your {symbol} setup confirmed as {confirmed_action}. "
            f"{confirmation_reason or 'You can review levels and record whether you entered.'}"
        ),
        link=f"/confirm/{watch_id}",
        meta={
            "watch_id": watch_id,
            "symbol": symbol,
            "confirmed_action": confirmed_action,
            "wait_reason": wait_reason,
            "confirmation_reason": confirmation_reason,
        },
    )


def notify_feedback_due(user_id: int, *, prediction_id: int, symbol: str, predicted_action: str) -> None:
    create_notification(
        user_id,
        kind="feedback_due",
        title=f"Optional — {symbol} trade check-in",
        body=f"Did you enter the {symbol} {predicted_action} signal? You can record this anytime.",
        link="/feedback",
        meta={"prediction_id": prediction_id, "symbol": symbol, "predicted_action": predicted_action},
    )


def notify_quota_request(user_id: int, *, username: str, message: str | None, signals_remaining: int) -> None:
    body = message.strip() if message else "User requested additional prediction quota."
    notify_admins(
        kind="quota_request",
        title=f"Quota request — {username}",
        body=f"{body} (current quota: {signals_remaining})",
        link=f"/users/{user_id}",
        meta={
            "user_id": user_id,
            "username": username,
            "signals_remaining": signals_remaining,
            "message": message,
        },
    )


def notify_quota_updated(user_id: int, *, signals_remaining: int, reason: str = "updated") -> None:
    create_notification(
        user_id,
        kind="quota_updated",
        title="Prediction quota updated",
        body=f"Your quota was {reason}. You now have {signals_remaining} predictions remaining.",
        link="/predict",
        meta={"signals_remaining": signals_remaining, "reason": reason},
    )


def recent_quota_request_exists(user_id: int, within_hours: int = 24) -> bool:
    """Avoid spamming admins with duplicate quota requests."""
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(hours=within_hours)
        row = (
            db.query(Notification)
            .filter(
                Notification.kind == "quota_request",
                Notification.created_at >= since,
            )
            .order_by(Notification.id.desc())
            .limit(200)
            .all()
        )
        for n in row:
            if not n.meta_json:
                continue
            try:
                meta = json.loads(n.meta_json)
            except json.JSONDecodeError:
                continue
            if meta.get("user_id") == user_id:
                return True
        return False
    finally:
        db.close()
