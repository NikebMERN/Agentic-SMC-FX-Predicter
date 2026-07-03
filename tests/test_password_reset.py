# tests/test_password_reset.py
"""Forgot-password and change-password flows on the admin panel."""
import re

import pytest


@pytest.fixture()
def outbox(monkeypatch):
    """Capture outgoing mail instead of hitting SMTP."""
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    from utils import mailer
    monkeypatch.setattr(mailer, "send_email", fake_send)
    return sent


def code_from(mail):
    return re.search(r"\b(\d{6})\b", mail["body"]).group(1)


def test_forgot_is_enumeration_safe(client, outbox):
    r1 = client.post("/admin/api/forgot", json={"email": "nobody@test.local"})
    r2 = client.post("/admin/api/forgot", json={"email": "admin@test.local"})
    assert r1.status_code == r2.status_code == 200
    assert r1.get_json()["message"] == r2.get_json()["message"]
    assert len(outbox) == 1  # mail only actually goes to the real admin
    assert outbox[0]["to"] == "admin@test.local"


def test_full_reset_flow(client, outbox):
    client.post("/admin/api/forgot", json={"email": "admin@test.local"})
    code = code_from(outbox[-1])

    # wrong code rejected, correct one accepted
    bad = client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": "000000" if code != "000000" else "111111",
        "new_password": "brand-new-pass"})
    assert bad.status_code == 400

    weak = client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": code, "new_password": "short"})
    assert weak.status_code == 400

    ok = client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": code, "new_password": "brand-new-pass"})
    assert ok.status_code == 200, ok.get_json()

    # the code is single-use
    again = client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": code, "new_password": "another-pass-1"})
    assert again.status_code == 400

    # old password dead, new password works
    assert client.post("/admin/api/login", json={
        "email": "admin@test.local", "password": "test-admin-pass"}).status_code == 401
    assert client.post("/admin/api/login", json={
        "email": "admin@test.local", "password": "brand-new-pass"}).status_code == 200

    # restore the original password for the other tests
    client.post("/admin/api/forgot", json={"email": "admin@test.local"})
    client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": code_from(outbox[-1]),
        "new_password": "test-admin-pass"})


def test_reset_code_burns_after_max_attempts(client, outbox):
    client.post("/admin/api/forgot", json={"email": "admin@test.local"})
    code = code_from(outbox[-1])
    wrong = "999999" if code != "999999" else "888888"
    for _ in range(5):
        client.post("/admin/api/reset", json={
            "email": "admin@test.local", "code": wrong, "new_password": "whatever-pass"})
    # even the right code is dead now
    r = client.post("/admin/api/reset", json={
        "email": "admin@test.local", "code": code, "new_password": "whatever-pass"})
    assert r.status_code == 400


def test_change_password_requires_current(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    assert client.post("/admin/api/change-password", headers=h, json={
        "current_password": "wrong", "new_password": "some-new-pass"}).status_code == 401
    assert client.post("/admin/api/change-password", headers=h, json={
        "current_password": "test-admin-pass", "new_password": "tiny"}).status_code == 400

    ok = client.post("/admin/api/change-password", headers=h, json={
        "current_password": "test-admin-pass", "new_password": "roundtrip-pass"})
    assert ok.status_code == 200
    # change it back
    client.post("/admin/api/change-password", headers=h, json={
        "current_password": "roundtrip-pass", "new_password": "test-admin-pass"})


def test_forgot_for_regular_user_sends_nothing(client, outbox):
    client.post("/register", json={
        "username": "dave", "email": "dave@test.local", "password": "pw123456"})
    r = client.post("/admin/api/forgot", json={"email": "dave@test.local"})
    assert r.status_code == 200  # generic response either way
    assert outbox == []          # but no admin reset mail for non-admins
