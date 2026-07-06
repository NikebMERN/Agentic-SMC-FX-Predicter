"""User-configurable Telegram alert rules with 15m scanner."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from db.models import AlertEvent, AlertRule, PredictionReview
from db.session import SessionLocal
from engine.pipeline import predict_symbol
from services.notifier import send_message
from utils.compliance import DISCLAIMER
from utils.logger import get_logger

log = get_logger("services.alert_scanner")

DEDUPE_HOURS = 4


def _parse_json(raw: str, default):
    try:
        return json.loads(raw) if raw else default
    except json.JSONDecodeError:
        return default


def list_rules(user_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(AlertRule).filter(AlertRule.user_id == user_id).order_by(AlertRule.id.desc()).all()
        return [_serialize_rule(r) for r in rows]
    finally:
        db.close()


def create_rule(user_id: int, data: dict) -> AlertRule | None:
    db = SessionLocal()
    try:
        row = AlertRule(
            user_id=user_id,
            channel=data.get("channel", "TELEGRAM"),
            telegram_chat_id=data.get("telegram_chat_id"),
            pairs_json=json.dumps(data.get("pairs", [])),
            min_confidence=float(data.get("min_confidence", 0.6)),
            allowed_directions_json=json.dumps(data.get("allowed_directions", ["BUY_BIAS", "SELL_BIAS"])),
            timeframes_json=json.dumps(data.get("timeframes", ["60min"])),
            trading_style=data.get("trading_style", "intraday"),
            quiet_hours_json=json.dumps(data.get("quiet_hours")) if data.get("quiet_hours") else None,
            max_alerts_per_day=int(data.get("max_alerts_per_day", 10)),
            is_active=bool(data.get("is_active", True)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        log.exception("Create alert rule failed")
        db.rollback()
        return None
    finally:
        db.close()


def update_rule(rule_id: int, user_id: int, data: dict) -> bool:
    db = SessionLocal()
    try:
        row = db.query(AlertRule).filter(AlertRule.id == rule_id, AlertRule.user_id == user_id).first()
        if not row:
            return False
        for field, attr in (
            ("channel", "channel"),
            ("telegram_chat_id", "telegram_chat_id"),
            ("trading_style", "trading_style"),
            ("min_confidence", "min_confidence"),
            ("max_alerts_per_day", "max_alerts_per_day"),
            ("is_active", "is_active"),
        ):
            if field in data:
                setattr(row, attr, data[field])
        if "pairs" in data:
            row.pairs_json = json.dumps(data["pairs"])
        if "allowed_directions" in data:
            row.allowed_directions_json = json.dumps(data["allowed_directions"])
        if "timeframes" in data:
            row.timeframes_json = json.dumps(data["timeframes"])
        if "quiet_hours" in data:
            row.quiet_hours_json = json.dumps(data["quiet_hours"]) if data["quiet_hours"] else None
        row.updated_at = datetime.utcnow()
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def delete_rule(rule_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        row = db.query(AlertRule).filter(AlertRule.id == rule_id, AlertRule.user_id == user_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def _serialize_rule(row: AlertRule) -> dict:
    return {
        "id": row.id,
        "channel": row.channel,
        "telegram_chat_id": row.telegram_chat_id,
        "pairs": _parse_json(row.pairs_json, []),
        "min_confidence": row.min_confidence,
        "allowed_directions": _parse_json(row.allowed_directions_json, []),
        "timeframes": _parse_json(row.timeframes_json, []),
        "trading_style": row.trading_style,
        "quiet_hours": _parse_json(row.quiet_hours_json, None),
        "max_alerts_per_day": row.max_alerts_per_day,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _in_quiet_hours(rule: AlertRule) -> bool:
    qh = _parse_json(rule.quiet_hours_json, None)
    if not qh:
        return False
    now = datetime.utcnow()
    start_h = int(qh.get("start_hour", 22))
    end_h = int(qh.get("end_hour", 6))
    if start_h <= end_h:
        return start_h <= now.hour < end_h
    return now.hour >= start_h or now.hour < end_h


def _daily_count(rule_id: int) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    db = SessionLocal()
    try:
        return (
            db.query(AlertEvent)
            .filter(AlertEvent.alert_rule_id == rule_id, AlertEvent.sent_at >= since, AlertEvent.status == "SENT")
            .count()
        )
    finally:
        db.close()


def _recent_duplicate(rule_id: int, symbol: str, action: str, interval: str) -> bool:
    since = datetime.utcnow() - timedelta(hours=DEDUPE_HOURS)
    db = SessionLocal()
    try:
        events = (
            db.query(AlertEvent, PredictionReview)
            .join(PredictionReview, AlertEvent.prediction_id == PredictionReview.id, isouter=True)
            .filter(AlertEvent.alert_rule_id == rule_id, AlertEvent.sent_at >= since)
            .all()
        )
        for _, pr in events:
            if pr and pr.symbol == symbol and pr.predicted_action == action and pr.interval == interval:
                return True
        return False
    finally:
        db.close()


def _format_alert(result: dict) -> str:
    d = result.get("decision") or {}
    sym = result.get("symbol", "")
    action = d.get("action", "NO_TRADE")
    conf = d.get("confidence", 0)
    lines = [
        f"SmartFlow alert — {sym}",
        f"Signal: {action} ({conf:.0%} confidence)",
        f"Style: {result.get('trading_style', 'intraday')} | TF: {result.get('interval')}",
    ]
    if d.get("entry"):
        lines.append(f"Entry: {d['entry']}")
    if d.get("stop_loss"):
        lines.append(f"SL: {d['stop_loss']}")
    if d.get("take_profit"):
        lines.append(f"TP: {d['take_profit']}")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def run_alert_scan() -> int:
    db = SessionLocal()
    try:
        rules = db.query(AlertRule).filter(AlertRule.is_active == True).all()  # noqa: E712
    finally:
        db.close()

    sent = 0
    for rule in rules:
        if _in_quiet_hours(rule) or _daily_count(rule.id) >= rule.max_alerts_per_day:
            continue
        pairs = _parse_json(rule.pairs_json, [])
        directions = _parse_json(rule.allowed_directions_json, [])
        timeframes = _parse_json(rule.timeframes_json, ["60min"])
        for pair in pairs:
            for tf in timeframes:
                try:
                    result = predict_symbol(pair, interval=tf, fetch=False, trading_style=rule.trading_style)
                except Exception:
                    continue
                decision = result.get("decision") or {}
                action = decision.get("action", "")
                conf = float(decision.get("confidence", 0))
                if action not in directions or conf < rule.min_confidence:
                    continue
                if _recent_duplicate(rule.id, pair.upper(), action, tf):
                    continue
                chat_id = rule.telegram_chat_id
                if not chat_id:
                    continue
                msg = _format_alert(result)
                ok = send_message(chat_id, msg)
                db = SessionLocal()
                try:
                    db.add(AlertEvent(
                        alert_rule_id=rule.id,
                        status="SENT" if ok else "FAILED",
                        error_message=None if ok else "send_failed",
                    ))
                    db.commit()
                finally:
                    db.close()
                if ok:
                    sent += 1
    if sent:
        log.info("Alert scan sent %d message(s)", sent)
    return sent
