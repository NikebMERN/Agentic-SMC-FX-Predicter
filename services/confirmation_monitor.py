# services/confirmation_monitor.py
"""Watch WAIT_FOR_CONFIRMATION setups and notify users when they confirm."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from db.models import ConfirmationWatch
from db.session import SessionLocal
from engine.confluence import ACTION_WAIT, is_trade_action
from engine.pipeline import predict_symbol
from services.notification_service import notify_confirmation_ready
from services.notifier import notify_user
from services.prediction_record import record_prediction_from_result
from services.prediction_review import list_reviews, parse_horizon
from utils.compliance import assert_safe_wording
from utils.logger import get_logger

log = get_logger("services.confirmation_monitor")

SCAN_MINUTES = int(os.getenv("CONFIRMATION_SCAN_MINUTES", "15"))
WATCH_TTL_HOURS = int(os.getenv("CONFIRMATION_WATCH_TTL_HOURS", "48"))


def extract_wait_reason(decision: dict) -> str:
    reasons = decision.get("reasoning") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    for reason in reasons:
        text = str(reason)
        lower = text.lower()
        if any(k in lower for k in ("confirm", "mss", "choch", "await")):
            return text
    invalid = decision.get("invalid_reasons") or decision.get("no_trade_reasons") or []
    if invalid:
        return "; ".join(str(x) for x in invalid[:2])
    if reasons:
        return str(reasons[-1])
    return "Lower-timeframe confirmation (MSS/CHoCH) required before entry."


def extract_confirmation_reason(decision: dict) -> str:
    reasons = decision.get("reasoning") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    for reason in reasons:
        text = str(reason)
        lower = text.lower()
        if any(k in lower for k in ("confirm", "mss", "choch")):
            return text
    if reasons:
        return str(reasons[0])
    action = decision.get("action", "active")
    return f"Setup confirmed — trade bias is now {action}."


def _predict_params(result: dict) -> dict:
    mtf_ctx = result.get("mtf_context") or {}
    return {
        "interval": result.get("interval"),
        "mtf": bool(mtf_ctx.get("enabled") or result.get("mtf")),
        "strategy_mode": result.get("strategy", "both"),
        "trading_style": result.get("trading_style", "intraday"),
        "fetch": True,
    }


def _trim_snapshot(result: dict) -> dict:
    keep = (
        "symbol", "interval", "strategy", "trading_style", "decision", "prediction",
        "analysis_summary", "structured_signals", "feature_snapshot", "meta_feature_snapshot",
        "candle_snapshot", "mtf_context", "ml", "threshold_version_id",
    )
    return {k: result[k] for k in keep if k in result}


def maybe_create_watch(*, user_id: int | None, review, result: dict) -> ConfirmationWatch | None:
    if not user_id or not review:
        return None
    decision = result.get("decision") or {}
    if decision.get("action") != ACTION_WAIT:
        return None

    db = SessionLocal()
    try:
        existing = (
            db.query(ConfirmationWatch)
            .filter(
                ConfirmationWatch.source_review_id == review.id,
                ConfirmationWatch.status == "watching",
            )
            .first()
        )
        if existing:
            return existing

        _, horizon_hours = parse_horizon(result.get("trading_style") or review.horizon)
        now = datetime.utcnow()
        expires = now + timedelta(hours=max(WATCH_TTL_HOURS, horizon_hours * 2))
        row = ConfirmationWatch(
            user_id=user_id,
            source_review_id=review.id,
            symbol=str(result.get("symbol", review.symbol)).upper(),
            interval=result.get("interval") or review.interval or "60min",
            horizon=review.horizon or "intraday",
            strategy_mode=result.get("strategy") or review.strategy_mode or "both",
            trading_style=result.get("trading_style") or review.trading_style or "intraday",
            params_json=json.dumps(_predict_params(result)),
            status="watching",
            wait_reason=extract_wait_reason(decision),
            expires_at=expires,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        log.info(
            "Confirmation watch #%s for user %s %s (review #%s)",
            row.id, user_id, row.symbol, review.id,
        )
        return row
    except Exception:
        log.exception("Failed to create confirmation watch for review %s", getattr(review, "id", "?"))
        db.rollback()
        return None
    finally:
        db.close()


def _serialize_watch(row: ConfirmationWatch, *, review: dict | None = None) -> dict:
    snapshot = None
    if row.confirmed_snapshot_json:
        try:
            snapshot = json.loads(row.confirmed_snapshot_json)
        except json.JSONDecodeError:
            snapshot = None
    decision = (snapshot or {}).get("decision") or {}
    return {
        "id": row.id,
        "status": row.status,
        "symbol": row.symbol,
        "interval": row.interval,
        "horizon": row.horizon,
        "strategy_mode": row.strategy_mode,
        "trading_style": row.trading_style,
        "source_review_id": row.source_review_id,
        "confirmed_review_id": row.confirmed_review_id,
        "wait_reason": row.wait_reason,
        "confirmed_action": row.confirmed_action,
        "confirmation_reason": row.confirmation_reason,
        "notified_at": row.notified_at.isoformat() if row.notified_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "snapshot": snapshot,
        "decision": decision or None,
        "review": review,
    }


def get_watch(user_id: int, watch_id: int) -> dict | None:
    db = SessionLocal()
    try:
        row = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.id == watch_id, ConfirmationWatch.user_id == user_id)
            .first()
        )
        if not row:
            return None
        review = None
        if row.confirmed_review_id:
            reviews = list_reviews(user_id=user_id, limit=5)
            review = next((r for r in reviews if r["id"] == row.confirmed_review_id), None)
            if not review:
                review = next(
                    (r for r in list_reviews(user_id=user_id, limit=200) if r["id"] == row.confirmed_review_id),
                    None,
                )
        return _serialize_watch(row, review=review)
    finally:
        db.close()


def _load_params(row: ConfirmationWatch) -> dict:
    if not row.params_json:
        return {"fetch": True, "mtf": True, "strategy_mode": row.strategy_mode or "both"}
    try:
        params = json.loads(row.params_json)
    except json.JSONDecodeError:
        params = {}
    params.setdefault("fetch", True)
    params.setdefault("strategy_mode", row.strategy_mode or "both")
    params.setdefault("trading_style", row.trading_style or row.horizon or "intraday")
    return params


def _run_predict(row: ConfirmationWatch) -> dict:
    params = _load_params(row)
    interval = params.get("interval")
    mtf = params.get("mtf")
    if interval in ("", "mtf", "multi"):
        interval = None
    return predict_symbol(
        row.symbol,
        interval=interval,
        fetch=bool(params.get("fetch", True)),
        strategy_mode=params.get("strategy_mode", row.strategy_mode or "both"),
        mtf=bool(mtf) if mtf is not None else None,
        trading_style=params.get("trading_style", row.trading_style or "intraday"),
    )


def _notify_confirmed(row: ConfirmationWatch, decision: dict) -> None:
    notify_confirmation_ready(
        row.user_id,
        watch_id=row.id,
        symbol=row.symbol,
        confirmed_action=row.confirmed_action or decision.get("action", ""),
        wait_reason=row.wait_reason or "",
        confirmation_reason=row.confirmation_reason or "",
    )
    tg = assert_safe_wording(
        f"Setup confirmed — {row.symbol} {row.confirmed_action} is ready to enter.\n\n"
        f"You were waiting for: {row.wait_reason or 'confirmation'}\n"
        f"Confirmation: {row.confirmation_reason or 'Trade bias is now active.'}\n\n"
        f"Open the app to review levels and record whether you entered."
    )
    notify_user(row.user_id, tg)


def _mark_confirmed(row: ConfirmationWatch, result: dict) -> None:
    decision = result.get("decision") or {}
    row.status = "confirmed"
    row.confirmed_action = decision.get("action")
    row.confirmation_reason = extract_confirmation_reason(decision)
    row.confirmed_snapshot_json = json.dumps(_trim_snapshot(result), default=str)
    row.updated_at = datetime.utcnow()
    if not row.notified_at:
        row.notified_at = datetime.utcnow()
        _notify_confirmed(row, decision)


def scan_watches(*, force: bool = False) -> int:
    """Re-check active watches; notify when a setup confirms. Returns notify count."""
    now = datetime.utcnow()
    min_gap = timedelta(minutes=SCAN_MINUTES)
    db = SessionLocal()
    try:
        rows = (
            db.query(ConfirmationWatch)
            .filter(
                ConfirmationWatch.status == "watching",
                ConfirmationWatch.expires_at > now,
            )
            .all()
        )
        watch_ids = [r.id for r in rows]
    finally:
        db.close()

    notified = 0
    for watch_id in watch_ids:
        db = SessionLocal()
        try:
            row = db.query(ConfirmationWatch).filter(ConfirmationWatch.id == watch_id).first()
            if not row or row.status != "watching":
                continue
            if row.expires_at <= now:
                row.status = "expired"
                row.updated_at = now
                db.commit()
                continue
            if not force and row.last_checked_at and (now - row.last_checked_at) < min_gap:
                continue

            result = _run_predict(row)
            row.last_checked_at = now
            decision = result.get("decision") or {}
            action = decision.get("action")
            if is_trade_action(action):
                _mark_confirmed(row, result)
                db.commit()
                notified += 1
                log.info("Confirmation watch #%s confirmed as %s", row.id, action)
            else:
                row.updated_at = now
                db.commit()
        except Exception:
            log.exception("Confirmation scan failed for watch %s", watch_id)
            db.rollback()
        finally:
            db.close()
    return notified


def materialize_review(user_id: int, watch_id: int) -> tuple[bool, str, dict | None]:
    db = SessionLocal()
    try:
        row = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.id == watch_id, ConfirmationWatch.user_id == user_id)
            .first()
        )
        if not row:
            return False, "Confirmation watch not found", None
        if row.status != "confirmed":
            return False, "Setup has not confirmed yet", None
        if row.confirmed_review_id:
            reviews = list_reviews(user_id=user_id, limit=200)
            review = next((r for r in reviews if r["id"] == row.confirmed_review_id), None)
            if review:
                return True, "Review ready", get_watch(user_id, watch_id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.id == watch_id, ConfirmationWatch.user_id == user_id)
            .first()
        )
        if not row or not row.confirmed_snapshot_json:
            return False, "Confirmed snapshot missing", None
        result = json.loads(row.confirmed_snapshot_json)
        review = record_prediction_from_result(
            user_id=user_id,
            result=result,
            horizon=row.horizon or "intraday",
            source="confirmation",
        )
        if not review:
            return False, "Could not create review", None
        row.confirmed_review_id = review.id
        row.updated_at = datetime.utcnow()
        db.commit()
        return True, "Review ready", get_watch(user_id, watch_id)
    except Exception:
        log.exception("materialize_review failed for watch %s", watch_id)
        db.rollback()
        return False, "Could not create review", None
    finally:
        db.close()


def analyze_fresh(user_id: int, watch_id: int) -> tuple[bool, str, dict | None]:
    db = SessionLocal()
    try:
        row = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.id == watch_id, ConfirmationWatch.user_id == user_id)
            .first()
        )
        if not row:
            return False, "Confirmation watch not found", None
        if row.status != "confirmed":
            return False, "Setup has not confirmed yet", None
    finally:
        db.close()

    from services.user_access import decrement_quota, increment_quota

    ok, quota_msg = decrement_quota(user_id)
    if not ok:
        return False, quota_msg, None

    db = SessionLocal()
    try:
        row = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.id == watch_id, ConfirmationWatch.user_id == user_id)
            .first()
        )
        if not row:
            increment_quota(user_id)
            return False, "Confirmation watch not found", None
        result = _run_predict(row)
        review = record_prediction_from_result(
            user_id=user_id,
            result=result,
            horizon=row.horizon or "intraday",
            source="confirmation_analyze",
        )
        if not review:
            increment_quota(user_id)
            return False, "Analysis failed", None
        row.confirmed_review_id = review.id
        row.confirmed_snapshot_json = json.dumps(_trim_snapshot(result), default=str)
        decision = result.get("decision") or {}
        row.confirmed_action = decision.get("action")
        row.confirmation_reason = extract_confirmation_reason(decision)
        row.updated_at = datetime.utcnow()
        db.commit()
        payload = get_watch(user_id, watch_id) or {}
        payload["analyze_result"] = result
        payload["quota"] = quota_msg
        return True, "Analysis complete", payload
    except Exception as exc:
        increment_quota(user_id)
        log.exception("analyze_fresh failed for watch %s", watch_id)
        return False, str(exc), None
    finally:
        db.close()
