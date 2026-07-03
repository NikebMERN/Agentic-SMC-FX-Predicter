# tests/test_quota_refund.py
from unittest.mock import patch

import app as app_module
from tests.helpers import auth, register_and_login


def _quota(client, token):
    res = client.get("/me", headers=auth(token))
    assert res.status_code == 200
    return res.get_json()["signals_remaining"]


def test_analyze_refunds_quota_on_predict_failure(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="quotauser",
        email="quota@test.local",
        password="SecurePass123!",
        quota=10,
    )
    token = user["token"]
    before = _quota(client, token)

    with patch.object(app_module, "predict_symbol", side_effect=RuntimeError("predict failed")):
        res = client.post(
            "/analyze",
            headers=auth(token),
            json={"symbol": "EURUSD", "fetch": False},
        )
    assert res.status_code == 500
    assert _quota(client, token) == before


def test_predict_stream_refunds_quota_on_failure(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="quotapred",
        email="quotapred@test.local",
        password="SecurePass123!",
        quota=10,
    )
    token = user["token"]
    before = _quota(client, token)

    acc = client.post(
        "/accounts/create",
        headers=auth(token),
        json={"name": "Test", "balance": 1000, "risk_pct": 0.01},
    )
    assert acc.status_code == 200, acc.get_json()
    account_id = acc.get_json()["account"]["id"]

    with patch.object(app_module, "predict_symbol", side_effect=RuntimeError("predict failed")):
        res = client.post(
            f"/predict/{account_id}",
            headers=auth(token),
            json={"symbol": "EURUSD"},
        )
        assert res.status_code == 200
        data = res.get_data(as_text=True)
    assert "predict failed" in data or "[ERROR]" in data
    assert _quota(client, token) == before
