# tests/test_api_extras.py
"""Health, auth, close-trade, audit, and public password reset."""
from tests.helpers import register_and_login


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code in (200, 503)
    body = res.get_json()
    assert "database" in body
    assert "status" in body


def test_close_trade_requires_auth(client):
    assert client.post("/close-trade/1").status_code == 401


def test_close_trade_rejects_other_users_trade(client, admin_token):
    from db.session import SessionLocal
    from db.models import User, Account, Trade

    body_a = register_and_login(
        client, admin_token,
        username="trader1", email="trader1@test.local", password="pw12345678",
    )
    token_a = body_a["token"]
    body_b = register_and_login(
        client, admin_token,
        username="trader2", email="trader2@test.local", password="pw12345678",
    )
    token_b = body_b["token"]

    db = SessionLocal()
    try:
        u1 = db.query(User).filter(User.email == body_a["email"]).first()
        acct = Account(user_id=u1.id, name="main", balance=1000.0)
        db.add(acct)
        db.commit()
        db.refresh(acct)
        trade = Trade(
            user_id=u1.id, account_id=acct.id, symbol="EURUSD", side="BUY",
            status="OPEN", entry_price=1.1, stop_loss=1.09, take_profit=1.12,
            lot_size=0.01, confidence=0.6,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        trade_id = trade.id
    finally:
        db.close()

    assert client.post(f"/close-trade/{trade_id}", headers=auth(token_b)).status_code == 403


def test_audit_log_after_promote(client, admin_token):
    register_and_login(
        client, admin_token,
        username="auditme", email="auditme@test.local", password="pw12345678",
    )
    users = client.get("/admin/api/users?q=auditme", headers=auth(admin_token)).get_json()["users"]
    uid = users[0]["id"]
    client.post(f"/admin/api/users/{uid}/role", headers=auth(admin_token), json={"role": "admin"})
    logs = client.get("/admin/api/audit?action=set_role", headers=auth(admin_token)).get_json()["logs"]
    assert any(l["target_id"] == str(uid) for l in logs)


def test_public_forgot_password_enumeration_safe(client):
    res = client.post("/forgot-password", json={"email": "nobody@test.local"})
    assert res.status_code == 200
    assert "registered" in res.get_json()["message"].lower()


def test_refresh_token_flow(client, admin_token):
    body = register_and_login(
        client, admin_token,
        username="ref1", email="ref1@test.local", password="pw12345678",
    )
    login = client.post("/login", json={"email": body["email"], "password": "pw12345678"})
    body = login.get_json()
    assert "refresh_token" in body
    refreshed = client.post("/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.get_json()


def test_telegram_link_code(client, admin_token):
    body = register_and_login(
        client, admin_token,
        username="tg1", email="tg1@test.local", password="pw12345678",
    )
    token = body["token"]
    res = client.post("/telegram/link-code", headers=auth(token))
    assert res.status_code == 200
    assert "code" in res.get_json()


def test_telegram_redeem_merges_after_bot_start(client, admin_token):
    from services.telegram_link import create_link_code, redeem_link_code, get_user_by_chat
    from services.user_service import register_telegram_user

    suffix = __import__("uuid").uuid4().hex[:8]
    reg = client.post("/register", json={
        "username": f"tgmerge_{suffix}",
        "email": f"tgmerge_{suffix}@test.local",
        "password": "pw12345678",
    })
    assert reg.status_code == 201
    web_user_id = reg.get_json()["user_id"]
    client.post(
        f"/admin/api/users/{web_user_id}/approve",
        headers=auth(admin_token),
        json={"signals_remaining": 5},
    )

    register_telegram_user("888777", "botuser", "Bot")
    code = create_link_code(web_user_id)
    result = redeem_link_code("888777", code)
    assert result.get("success"), result
    linked = get_user_by_chat("888777")
    assert linked is not None
    assert linked.id == web_user_id


def test_new_user_is_active_with_trial_quota(client):
    """Registration policy: new accounts are ACTIVE immediately with the
    free trial quota (web and Telegram alike)."""
    import uuid
    from services.user_access import DEFAULT_SIGNALS_QUOTA
    suffix = uuid.uuid4().hex[:8]
    email = f"trial_{suffix}@test.local"
    reg = client.post("/register", json={
        "username": f"trial_{suffix}", "email": email, "password": "pw12345678",
    })
    assert reg.status_code == 201
    body = reg.get_json()
    assert body["status"] == "active"
    assert body["signals_remaining"] == DEFAULT_SIGNALS_QUOTA
    assert str(DEFAULT_SIGNALS_QUOTA) in body["message"]

    login = client.post("/login", json={"email": email, "password": "pw12345678"})
    assert login.status_code == 200
    assert login.get_json()["status"] == "active"
    token = login.get_json()["token"]
    me = client.get("/me", headers=auth(token))
    assert me.status_code == 200
    assert me.get_json()["status"] == "active"
    assert me.get_json()["signals_remaining"] == DEFAULT_SIGNALS_QUOTA
