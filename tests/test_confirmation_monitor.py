# tests/test_confirmation_monitor.py
"""Confirmation watch creation and notify-on-confirm."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from db.models import ConfirmationWatch, NotificationDelivery, User
from db.session import SessionLocal
from services.confirmation_monitor import (
    extract_wait_reason,
    maybe_create_watch,
    scan_watches,
)
from services.notification_service import list_notifications
from services.prediction_record import record_prediction_from_result


def _wait_result(symbol="EURUSD"):
    return {
        "symbol": symbol,
        "interval": "60min",
        "strategy": "both",
        "trading_style": "intraday",
        "decision": {
            "action": "WAIT_FOR_CONFIRMATION",
            "confidence": 0.55,
            "entry": 1.1,
            "invalidation_price": 1.095,
            "target_liquidity": 1.11,
            "reasoning": ["Awaiting lower-TF entry confirmation (MSS/CHoCH)"],
        },
        "prediction": {"score": 62},
        "candle_snapshot": [],
    }


def _buy_result(symbol="EURUSD"):
    return {
        "symbol": symbol,
        "interval": "60min",
        "strategy": "both",
        "trading_style": "intraday",
        "decision": {
            "action": "BUY_BIAS",
            "confidence": 0.72,
            "entry": 1.101,
            "invalidation_price": 1.096,
            "target_liquidity": 1.112,
            "reasoning": ["MSS bullish confirmed on 15M"],
        },
        "prediction": {"score": 78},
        "candle_snapshot": [],
    }


@pytest.fixture
def approved_user(initialized_db, client, admin_token):
    from tests.helpers import auth, register_and_login

    user = register_and_login(
        client,
        admin_token,
        username="confuser",
        email="confuser@test.local",
        password="pass12345",
    )
    db = SessionLocal()
    try:
        row = db.query(User).filter(User.email == user["email"]).first()
        row.risk_disclosure_accepted_at = datetime.utcnow()
        db.commit()
        user["id"] = row.id
    finally:
        db.close()
    user["headers"] = auth(user["token"])
    return user


def test_extract_wait_reason_prefers_confirmation_line():
    reason = extract_wait_reason({
        "reasoning": ["HTF bullish", "Awaiting lower-TF entry confirmation (MSS/CHoCH)"],
    })
    assert "MSS" in reason


def test_maybe_create_watch_on_wait(approved_user):
    result = _wait_result()
    review = record_prediction_from_result(user_id=approved_user["id"], result=result, source="web")
    assert review is not None

    db = SessionLocal()
    try:
        watch = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.source_review_id == review.id)
            .first()
        )
        assert watch is not None
        assert watch.status == "watching"
        assert watch.user_id == approved_user["id"]
        assert "MSS" in (watch.wait_reason or "")
    finally:
        db.close()


def test_scan_notifies_when_setup_confirms(approved_user):
    result = _wait_result()
    review = record_prediction_from_result(user_id=approved_user["id"], result=result, source="web")
    db = SessionLocal()
    try:
        watch = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.source_review_id == review.id)
            .first()
        )
        watch_id = watch.id
    finally:
        db.close()

    with (
        patch("services.confirmation_monitor._run_predict", return_value=_buy_result()),
        patch("services.notification_queue.notify_user", return_value=True),
    ):
        scan_watches(force=True)

    db = SessionLocal()
    try:
        watch = db.query(ConfirmationWatch).filter(ConfirmationWatch.id == watch_id).first()
        assert watch.status == "confirmed"
        assert watch.confirmed_action == "BUY_BIAS"
        assert watch.notified_at is not None
    finally:
        db.close()

    notes = list_notifications(approved_user["id"])
    assert any(
        n["kind"] == "confirmation_ready" and n["link"] == f"/confirm/{watch_id}"
        for n in notes
    )


def test_confirmation_and_outbox_are_atomic(approved_user):
    result = _wait_result("GBPUSD")
    review = record_prediction_from_result(user_id=approved_user["id"], result=result, source="web")
    db = SessionLocal()
    try:
        watch = db.query(ConfirmationWatch).filter(
            ConfirmationWatch.source_review_id == review.id
        ).first()
        watch_id = watch.id
    finally:
        db.close()

    with (
        patch("services.confirmation_monitor._run_predict", return_value=_buy_result("GBPUSD")),
        patch(
            "services.notification_queue.enqueue_event_in_session",
            side_effect=RuntimeError("outbox unavailable"),
        ),
    ):
        scan_watches(force=True)

    db = SessionLocal()
    try:
        watch = db.query(ConfirmationWatch).filter(ConfirmationWatch.id == watch_id).one()
        assert watch.status == "watching"
        assert watch.confirmed_action is None
    finally:
        db.close()


def test_stale_processing_delivery_is_recovered(approved_user):
    db = SessionLocal()
    try:
        delivery = NotificationDelivery(
            event_key="test:stale",
            user_id=approved_user["id"],
            channel="telegram",
            payload_json="{}",
            status="processing",
            attempts=1,
            updated_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db.add(delivery)
        db.commit()
        delivery_id = delivery.id
    finally:
        db.close()

    with patch("services.notification_queue._deliver", return_value=(True, None)):
        from services.notification_queue import process_pending
        result = process_pending()
    assert result["delivered"] >= 1

    db = SessionLocal()
    try:
        delivery = db.query(NotificationDelivery).filter(
            NotificationDelivery.id == delivery_id
        ).one()
        assert delivery.status == "delivered"
        assert delivery.attempts == 2
    finally:
        db.close()

def test_get_confirmation_api(client, approved_user):
    result = _wait_result()
    review = record_prediction_from_result(user_id=approved_user["id"], result=result, source="web")
    db = SessionLocal()
    try:
        watch = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.source_review_id == review.id)
            .first()
        )
        watch.status = "confirmed"
        watch.confirmed_action = "BUY_BIAS"
        watch.confirmation_reason = "MSS bullish confirmed on 15M"
        watch.confirmed_snapshot_json = __import__("json").dumps(_buy_result())
        watch.notified_at = datetime.utcnow()
        watch.expires_at = datetime.utcnow() + timedelta(hours=24)
        db.commit()
        watch_id = watch.id
    finally:
        db.close()

    res = client.get(f"/my/confirmations/{watch_id}", headers=approved_user["headers"])
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "confirmed"
    assert body["wait_reason"]
    assert body["confirmation_reason"]
    assert body["decision"]["action"] == "BUY_BIAS"


def test_materialize_creates_review(client, approved_user):
    result = _wait_result()
    review = record_prediction_from_result(user_id=approved_user["id"], result=result, source="web")
    db = SessionLocal()
    try:
        watch = (
            db.query(ConfirmationWatch)
            .filter(ConfirmationWatch.source_review_id == review.id)
            .first()
        )
        watch.status = "confirmed"
        watch.confirmed_action = "BUY_BIAS"
        watch.confirmation_reason = "Confirmed"
        watch.confirmed_snapshot_json = __import__("json").dumps(_buy_result())
        watch.notified_at = datetime.utcnow()
        db.commit()
        watch_id = watch.id
    finally:
        db.close()

    res = client.post(
        f"/my/confirmations/{watch_id}/materialize",
        headers=approved_user["headers"],
    )
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["review"]["can_record_trade_entry"] is True
    assert body["review"]["predicted_action"] == "BUY_BIAS"
