"""Durable multi-channel notification delivery with retries."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import requests
from sqlalchemy import and_, or_

from db.models import ConfirmationWatch, Notification, NotificationDelivery
from db.session import SessionLocal
from services.notification_service import create_notification
from services.notifier import notify_user
from utils.logger import get_logger

log = get_logger("services.notification_queue")
MAX_ATTEMPTS = int(os.getenv("NOTIFICATION_MAX_ATTEMPTS", "5"))
PROCESSING_TIMEOUT_SECONDS = int(os.getenv("NOTIFICATION_PROCESSING_TIMEOUT_SECONDS", "120"))
PUSH_WEBHOOK_URL = os.getenv("PUSH_NOTIFICATION_WEBHOOK", "").strip()


def enqueue_event_in_session(
    db,
    *,
    event_key: str,
    user_id: int,
    payload: dict,
    channels=None,
) -> int:
    channels = channels or ("website", "telegram", "push")
    created = 0
    serialized = json.dumps(payload, default=str)
    for channel in channels:
        exists = db.query(NotificationDelivery).filter(
            NotificationDelivery.event_key == event_key,
            NotificationDelivery.channel == channel,
        ).first()
        if exists:
            continue
        db.add(NotificationDelivery(
            event_key=event_key, user_id=user_id, channel=channel,
            payload_json=serialized,
        ))
        created += 1
    return created


def enqueue_event(*, event_key: str, user_id: int, payload: dict, channels=None) -> int:
    db = SessionLocal()
    try:
        created = enqueue_event_in_session(
            db, event_key=event_key, user_id=user_id,
            payload=payload, channels=channels,
        )
        db.commit()
        log.info("Queued notification event=%s channels=%s", event_key, created)
        return created
    except Exception:
        db.rollback()
        log.exception("Failed to queue notification event=%s", event_key)
        raise
    finally:
        db.close()


def format_confirmation_message(payload: dict) -> str:
    def value(name):
        raw = payload.get(name)
        return "N/A" if raw in (None, "") else raw
    return (
        f"Setup confirmed - {value('symbol')} {value('direction')}\n\n"
        f"Entry: {value('entry')}\nStop Loss: {value('stop_loss')}\n"
        f"Take Profit: {value('take_profit')}\nRisk Reward: {value('risk_reward')}\n"
        f"Confidence: {value('confidence')}\nLot size: {value('lot_size')}\n"
        f"Position size: {value('position_size')}\nStrategy: {value('strategy')}\n"
        f"Timeframe: {value('timeframe')}\nSession: {value('session')}\n"
        f"Trend: {value('trend')}\nConfluence score: {value('confluence_score')}\n"
        f"Confirmation reason: {value('confirmation_reason')}"
    )


def _deliver(row: NotificationDelivery, payload: dict) -> tuple[bool, str | None]:
    if row.channel == "website":
        db = SessionLocal()
        try:
            existing = db.query(Notification).filter(
                Notification.user_id == row.user_id,
                Notification.kind == "confirmation_ready",
                Notification.link == payload.get("link"),
            ).first()
            if existing:
                return True, None
        finally:
            db.close()
        note = create_notification(
            row.user_id, kind="confirmation_ready",
            title=f"Ready to enter - {payload.get('symbol')} {payload.get('direction')}",
            body=format_confirmation_message(payload), link=payload.get("link"), meta=payload,
        )
        return bool(note), None if note else "website notification insert failed"
    if row.channel == "telegram":
        ok = notify_user(row.user_id, format_confirmation_message(payload))
        return ok, None if ok else "Telegram account unavailable or delivery failed"
    if row.channel == "push":
        if not PUSH_WEBHOOK_URL:
            return True, "push unavailable"
        response = requests.post(
            PUSH_WEBHOOK_URL,
            json={"user_id": row.user_id, "event": row.event_key, "payload": payload},
            timeout=10,
        )
        return response.ok, None if response.ok else f"push HTTP {response.status_code}"
    return False, f"unknown channel {row.channel}"


def _sync_confirmation_delivery_status(event_key: str) -> None:
    if not event_key.startswith("confirmation:"):
        return
    try:
        watch_id = int(event_key.split(":", 1)[1])
    except (TypeError, ValueError):
        return
    db = SessionLocal()
    try:
        rows = db.query(NotificationDelivery).filter(
            NotificationDelivery.event_key == event_key
        ).all()
        if not rows:
            return
        statuses = {row.status for row in rows}
        watch = db.query(ConfirmationWatch).filter(ConfirmationWatch.id == watch_id).first()
        if not watch:
            return
        if statuses.issubset({"delivered", "skipped"}):
            watch.notified_at = watch.notified_at or datetime.utcnow()
        else:
            watch.notified_at = None
        db.commit()
    finally:
        db.close()


def process_pending(*, limit: int = 100) -> dict:
    now = datetime.utcnow()
    processing_cutoff = now - timedelta(seconds=PROCESSING_TIMEOUT_SECONDS)
    db = SessionLocal()
    try:
        ids = [item[0] for item in db.query(NotificationDelivery.id).filter(
            or_(
                and_(
                    NotificationDelivery.status.in_(("pending", "retry")),
                    NotificationDelivery.next_attempt_at <= now,
                ),
                and_(
                    NotificationDelivery.status == "processing",
                    NotificationDelivery.updated_at <= processing_cutoff,
                ),
            ),
        ).order_by(NotificationDelivery.id).limit(limit).all()]
    finally:
        db.close()

    result = {"delivered": 0, "skipped": 0, "retried": 0, "failed": 0}
    for delivery_id in ids:
        db = SessionLocal()
        try:
            row = db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).first()
            if not row or row.status not in ("pending", "retry", "processing"):
                continue
            row.status = "processing"
            row.attempts += 1
            db.commit()
            try:
                ok, detail = _deliver(row, json.loads(row.payload_json))
            except Exception as exc:
                ok, detail = False, str(exc)
            if ok:
                row.status = "skipped" if detail == "push unavailable" else "delivered"
                row.delivered_at = datetime.utcnow()
                row.last_error = detail
                result[row.status] += 1
            elif row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                row.last_error = detail
                result["failed"] += 1
            else:
                row.status = "retry"
                row.last_error = detail
                row.next_attempt_at = datetime.utcnow() + timedelta(seconds=min(300, 2 ** row.attempts * 5))
                result["retried"] += 1
            db.commit()
            log.info("Notification delivery #%s channel=%s status=%s", row.id, row.channel, row.status)
            _sync_confirmation_delivery_status(row.event_key)
        except Exception:
            log.exception("Notification delivery processing failed for #%s", delivery_id)
            db.rollback()
        finally:
            db.close()
    return result
