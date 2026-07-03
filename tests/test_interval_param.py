# tests/test_interval_param.py
from unittest.mock import patch

import app as app_module
from tests.helpers import auth, register_and_login


def test_analyze_rejects_invalid_interval(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="intervaluser",
        email="interval@test.local",
        password="SecurePass123!",
    )
    res = client.post(
        "/analyze",
        headers=auth(user["token"]),
        json={"symbol": "EURUSD", "interval": "2min", "fetch": False},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert "supported_intervals" in body
    assert "5min" in body["supported_intervals"]


def test_analyze_accepts_valid_interval(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="intervalok",
        email="intervalok@test.local",
        password="SecurePass123!",
    )
    fake = {
        "symbol": "EURUSD",
        "interval": "15min",
        "decision": {"action": "NO_TRADE", "confidence": 0.4, "entry": 1.1},
        "feature_snapshot": {},
    }
    with patch.object(app_module, "predict_symbol", return_value=fake) as mock_predict:
        res = client.post(
            "/analyze",
            headers=auth(user["token"]),
            json={"symbol": "EURUSD", "interval": "15min", "fetch": False},
        )
    assert res.status_code == 200, res.get_json()
    mock_predict.assert_called_once()
    assert mock_predict.call_args.kwargs.get("interval") == "15min"
