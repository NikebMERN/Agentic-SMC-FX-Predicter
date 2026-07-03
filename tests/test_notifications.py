# tests/test_notifications.py
"""In-app notification API."""
from tests.helpers import auth, register_and_login


def test_user_lists_notifications(client, admin_token):
    user = register_and_login(
        client, admin_token,
        username="notifuser", email="notif@test.local", password="pass12345",
    )
    res = client.get("/notifications", headers=auth(user["token"]))
    assert res.status_code == 200
    body = res.get_json()
    assert "notifications" in body
    assert "unread_count" in body
    assert any(n["kind"] == "quota_updated" for n in body["notifications"])


def test_quota_request_notifies_admin(client, admin_token):
    user = register_and_login(
        client, admin_token,
        username="quotareq", email="quotareq@test.local", password="pass12345",
        quota=0,
    )
    res = client.post(
        "/my/quota-request",
        headers=auth(user["token"]),
        json={"message": "Need more predictions please"},
    )
    assert res.status_code == 200, res.get_json()

    admin_res = client.get("/admin/api/notifications", headers=auth(admin_token))
    assert admin_res.status_code == 200
    notes = admin_res.get_json()["notifications"]
    assert any(n["kind"] == "quota_request" for n in notes)
    assert admin_res.get_json()["unread_count"] >= 1

    dup = client.post("/my/quota-request", headers=auth(user["token"]), json={})
    assert dup.status_code == 409


def test_mark_notification_read(client, admin_token):
    user = register_and_login(
        client, admin_token,
        username="readnotif", email="readnotif@test.local", password="pass12345",
        quota=0,
    )
    client.post("/my/quota-request", headers=auth(user["token"]), json={})

    admin_res = client.get("/admin/api/notifications", headers=auth(admin_token))
    note = admin_res.get_json()["notifications"][0]

    mark = client.patch(
        f"/admin/api/notifications/{note['id']}/read",
        headers=auth(admin_token),
    )
    assert mark.status_code == 200

    after = client.get("/admin/api/notifications?unread=1", headers=auth(admin_token))
    unread_ids = [n["id"] for n in after.get_json()["notifications"]]
    assert note["id"] not in unread_ids


def test_quota_update_notifies_user(client, admin_token):
    user = register_and_login(
        client, admin_token,
        username="quotaupd", email="quotaupd@test.local", password="pass12345",
        quota=1,
    )
    from db.models import User
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == user["email"]).first()
        user_id = u.id
    finally:
        db.close()

    client.post(
        f"/admin/api/users/{user_id}/quota",
        headers=auth(admin_token),
        json={"signals_remaining": 25},
    )

    res = client.get("/notifications", headers=auth(user["token"]))
    notes = res.get_json()["notifications"]
    assert any(n["kind"] == "quota_updated" for n in notes)
