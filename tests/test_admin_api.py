# tests/test_admin_api.py
"""Admin panel API: auth boundaries, user management, settings persistence."""
from tests.helpers import register_and_login


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_public_endpoints(client):
    assert client.get("/").status_code == 200
    body = client.get("/pairs").get_json()
    assert "EURUSD" in body["pairs"]


def test_admin_api_requires_admin_token(client, admin_token):
    assert client.get("/admin/api/overview").status_code == 401

    body = register_and_login(
        client, admin_token,
        username="bob", email="bob@test.local", password="pw123456",
    )
    user_token = body["token"]
    assert client.get("/admin/api/overview", headers=auth(user_token)).status_code == 403


def test_admin_login_rejects_non_admin(client, admin_token):
    body = register_and_login(
        client, admin_token,
        username="bob2", email="bob2@test.local", password="pw123456",
    )
    res = client.post("/admin/api/login",
                      json={"email": body["email"], "password": "pw123456"})
    assert res.status_code == 403


def test_overview_and_health(client, admin_token):
    body = client.get("/admin/api/overview", headers=auth(admin_token)).get_json()
    assert body["stats"]["users"] >= 1
    assert body["health"]["database"] is True
    assert isinstance(body["data_status"], list)


def test_ban_blocks_login_and_unban_restores(client, admin_token):
    body = register_and_login(
        client, admin_token,
        username="carol", email="carol@test.local", password="pw123456",
    )
    users = client.get("/admin/api/users?q=carol", headers=auth(admin_token)).get_json()["users"]
    carol_id = users[0]["id"]

    res = client.post(f"/admin/api/users/{carol_id}/ban",
                      headers=auth(admin_token), json={"banned": True})
    assert res.status_code == 200
    assert client.post("/login", json={
        "email": body["email"], "password": "pw123456"}).status_code == 403

    client.post(f"/admin/api/users/{carol_id}/ban",
                headers=auth(admin_token), json={"banned": False})
    assert client.post("/login", json={
        "email": body["email"], "password": "pw123456"}).status_code == 200


def test_admin_cannot_ban_or_demote_self(client, admin_token):
    users = client.get("/admin/api/users?q=admin@test.local",
                       headers=auth(admin_token)).get_json()["users"]
    admin_id = users[0]["id"]
    assert client.post(f"/admin/api/users/{admin_id}/ban",
                       headers=auth(admin_token), json={"banned": True}).status_code == 400
    assert client.post(f"/admin/api/users/{admin_id}/role",
                       headers=auth(admin_token), json={"role": "user"}).status_code == 400


def test_settings_roundtrip_and_validation(client, admin_token):
    res = client.post("/admin/api/settings", headers=auth(admin_token), json={
        "supported_pairs": "eurusd, gbpjpy", "min_final_confidence": "0.6"})
    assert res.status_code == 200, res.get_json()

    body = client.get("/admin/api/settings", headers=auth(admin_token)).get_json()
    effective = body["effective"]["supported_pairs"]
    assert "EURUSD" in effective
    assert "GBPJPY" in effective
    assert len(effective) >= 90
    assert body["effective"]["min_final_confidence"] == 0.6

    # the public /pairs endpoint reflects the full catalog
    public_pairs = client.get("/pairs").get_json()["pairs"]
    assert "EURUSD" in public_pairs
    assert len(public_pairs) >= 90

    # invalid values are rejected
    assert client.post("/admin/api/settings", headers=auth(admin_token),
                       json={"min_final_confidence": "2.0"}).status_code == 400
    assert client.post("/admin/api/settings", headers=auth(admin_token),
                       json={"supported_pairs": "NOTAPAIR123"}).status_code == 400


def test_manual_signal_creation(client, admin_token):
    res = client.post("/admin/api/signals", headers=auth(admin_token), json={
        "symbol": "eurusd", "side": "buy", "entry_price": 1.085, "confidence": 0.9})
    assert res.status_code == 200
    listed = client.get("/admin/api/signals?symbol=EURUSD",
                        headers=auth(admin_token)).get_json()["signals"]
    assert listed and listed[0]["side"] == "BUY"

    assert client.post("/admin/api/signals", headers=auth(admin_token),
                       json={"symbol": "EURUSD", "side": "HOLD",
                             "entry_price": 1.0}).status_code == 400


def test_overview_health_fields(client, admin_token):
    body = client.get("/admin/api/overview", headers=auth(admin_token)).get_json()
    h = body["health"]
    for key in (
        "data_provider_config", "active_provider", "live_fetch_available",
        "cache_pairs_count", "alpha_vantage_key_set", "any_api_key_set", "data_ready",
    ):
        assert key in h
    bt = body.get("latest_backtest")
    if bt:
        assert "summary" in bt or bt.get("symbol")


def test_user_detail_and_history(client, admin_token):
    from datetime import datetime, timedelta
    from db.session import SessionLocal
    from db.models import PredictionReview, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role == "user").first()
        if not user:
            return
        uid = user.id
        review = PredictionReview(
            user_id=uid,
            symbol="EURUSD",
            interval="60min",
            predicted_action="BUY_BIAS",
            predicted_confidence=0.7,
            entry_price=1.08,
            predicted_at=datetime.utcnow(),
            evaluate_at=datetime.utcnow() + timedelta(hours=2),
            status="pending",
        )
        db.add(review)
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/admin/api/users/{uid}", headers=auth(admin_token))
    assert detail.status_code == 200
    assert detail.get_json()["user"]["id"] == uid
    assert "counts" in detail.get_json()

    hist = client.get(f"/admin/api/users/{uid}/history", headers=auth(admin_token))
    assert hist.status_code == 200
    assert "predictions" in hist.get_json()


def test_delete_signal(client, admin_token):
    res = client.post("/admin/api/signals", headers=auth(admin_token), json={
        "symbol": "GBPUSD", "side": "SELL", "entry_price": 1.27, "confidence": 0.8})
    assert res.status_code == 200
    sid = res.get_json()["signal"]["id"]
    deleted = client.delete(f"/admin/api/signals/{sid}", headers=auth(admin_token))
    assert deleted.status_code == 200
    listed = client.get("/admin/api/signals?symbol=GBPUSD", headers=auth(admin_token)).get_json()["signals"]
    assert not any(s["id"] == sid for s in listed)


def test_backtest_persists_report(client, admin_token):
    import json
    import os

    res = client.post("/admin/api/backtest", headers=auth(admin_token), json={
        "symbol": "EURUSD", "fetch": False,
    })
    if res.status_code == 422:
        return
    assert res.status_code == 200
    body = res.get_json()
    assert body.get("saved_to_report") is True
    path = os.path.join(os.path.dirname(__file__), "..", "logs", "backtest_report.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    assert any(p.get("symbol") == "EURUSD" for p in report.get("pairs", []))


def test_refresh_status(client, admin_token):
    res = client.get("/admin/api/data/refresh/status", headers=auth(admin_token))
    assert res.status_code == 200
    assert "running" in res.get_json()
