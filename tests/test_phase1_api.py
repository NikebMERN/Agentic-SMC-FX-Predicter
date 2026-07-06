# tests/test_phase1_api.py
"""API tests for disclosure, feedback, training records."""
import json

import pytest


@pytest.fixture()
def approved_user(client):
    import uuid
    from db.session import SessionLocal
    from db.models import User
    from utils.security import hash_password, generate_token

    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        user = User(
            username=f"phase1_{suffix}",
            email=f"phase1_{suffix}@test.local",
            password_hash=hash_password("test-pass-123"),
            role="user",
            status="active",
            is_active=True,
            signals_remaining=10,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = generate_token(user.id)
        return {"id": user.id, "token": token}
    finally:
        db.close()


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_disclosure_gate_and_accept(client, approved_user):
    headers = {"Authorization": f"Bearer {approved_user['token']}"}
    r = client.post("/analyze", json={"symbol": "EURUSD", "fetch": False}, headers=headers)
    assert r.status_code == 403
    assert r.get_json().get("code") == "disclosure_required"

    acc = client.post("/me/accept-disclosure", headers=headers)
    assert acc.status_code == 200

    me = client.get("/me", headers=headers)
    assert me.get_json().get("risk_disclosure_accepted") is True


def test_feedback_trade_entry_and_outcome(client, approved_user):
    from datetime import datetime, timedelta
    from db.session import SessionLocal
    from db.models import PredictionReview, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == approved_user["id"]).first()
        user.risk_disclosure_accepted_at = datetime.utcnow()
        review = PredictionReview(
            user_id=user.id,
            symbol="EURUSD",
            interval="60min",
            predicted_action="BUY_BIAS",
            predicted_confidence=0.7,
            entry_price=1.1,
            predicted_at=datetime.utcnow(),
            feedback_due_at=datetime.utcnow() + timedelta(hours=2),
            evaluate_at=datetime.utcnow() + timedelta(hours=2),
            status="pending",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        rid = review.id
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {approved_user['token']}"}
    ok = client.post(
        f"/my/reviews/{rid}/feedback",
        json={"feedback": "ENTERED", "kind": "trade_entry"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.get_json().get("trade_entry") == "ENTERED"

    dup = client.post(
        f"/my/reviews/{rid}/feedback",
        json={"feedback": "DID_NOT_TAKE", "kind": "trade_entry"},
        headers=headers,
    )
    assert dup.status_code == 409

    outcome = client.post(
        f"/my/reviews/{rid}/feedback",
        json={"feedback": "SUCCESSFUL", "kind": "outcome"},
        headers=headers,
    )
    assert outcome.status_code == 200
    assert outcome.get_json().get("feedback") == "SUCCESSFUL"


def test_trade_entry_not_required_for_no_trade(client, approved_user):
    from datetime import datetime, timedelta
    from db.session import SessionLocal
    from db.models import PredictionReview

    db = SessionLocal()
    try:
        review = PredictionReview(
            user_id=approved_user["id"],
            symbol="EURUSD",
            interval="60min",
            predicted_action="NO_TRADE",
            predicted_confidence=0.5,
            entry_price=1.1,
            predicted_at=datetime.utcnow(),
            evaluate_at=datetime.utcnow() + timedelta(hours=2),
            status="pending",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        rid = review.id
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {approved_user['token']}"}
    listed = client.get("/my/reviews?limit=5", headers=headers)
    row = next(r for r in listed.get_json()["reviews"] if r["id"] == rid)
    assert row["feedback_required"] is False
    assert row["can_record_trade_entry"] is False
    assert row["can_record_outcome"] is False


def test_training_record_review_flow(client, admin_headers):
    from datetime import datetime, timedelta
    from db.session import SessionLocal
    from db.models import PredictionReview, TrainingRecord

    db = SessionLocal()
    try:
        review = PredictionReview(
            symbol="EURUSD",
            interval="60min",
            predicted_action="NO_TRADE",
            predicted_confidence=0.5,
            entry_price=1.1,
            predicted_at=datetime.utcnow(),
            evaluate_at=datetime.utcnow() + timedelta(hours=4),
            status="evaluated",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        rec = TrainingRecord(
            prediction_id=review.id,
            features_json=json.dumps({"rsi": 0.5}),
            final_label="flat",
            admin_status="PENDING_REVIEW",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        record_id = rec.id
    finally:
        db.close()

    listed = client.get("/admin/api/training-records?status=PENDING_REVIEW", headers=admin_headers)
    assert listed.status_code == 200
    ids = [r["id"] for r in listed.get_json()["records"]]
    assert record_id in ids

    patch = client.patch(
        f"/admin/api/training-records/{record_id}/review",
        json={"admin_status": "APPROVED", "admin_notes": "ok"},
        headers=admin_headers,
    )
    assert patch.status_code == 200
    assert patch.get_json()["record"]["admin_status"] == "APPROVED"


def test_analytics_shape(client, admin_headers):
    r = client.get("/admin/api/analytics", headers=admin_headers)
    assert r.status_code == 200
    data = r.get_json()
    for key in ("accuracy_by_pair", "calibration", "conflict_count", "verification_failure_count"):
        assert key in data


def test_my_history_and_candles(client, approved_user):
    from datetime import datetime, timedelta
    from db.session import SessionLocal
    from db.models import PredictionReview

    headers = {"Authorization": f"Bearer {approved_user['token']}"}
    db = SessionLocal()
    try:
        review = PredictionReview(
            user_id=approved_user["id"],
            symbol="EURUSD",
            interval="60min",
            predicted_action="BUY_BIAS",
            predicted_confidence=0.72,
            entry_price=1.085,
            target_price=1.09,
            invalidation_price=1.08,
            predicted_at=datetime.utcnow(),
            evaluate_at=datetime.utcnow() + timedelta(hours=2),
            status="pending",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        rid = review.id
    finally:
        db.close()

    hist = client.get("/my/history?hours=24", headers=headers)
    assert hist.status_code == 200
    body = hist.get_json()
    assert "stats_24h" in body
    assert body["stats_24h"]["total"] >= 1
    assert any(r["id"] == rid for r in body["reviews_24h"])

    candles = client.get(f"/my/reviews/{rid}/candles?bars=24", headers=headers)
    assert candles.status_code == 200
    cbody = candles.get_json()
    assert cbody["symbol"] == "EURUSD"
    assert cbody["interval"] == "60min"
    assert "candles" in cbody

    other = client.get(f"/my/reviews/{rid}/candles", headers={"Authorization": "Bearer invalid"})
    assert other.status_code == 401
