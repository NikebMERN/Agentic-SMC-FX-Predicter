from unittest.mock import patch

import pandas as pd

from engine.patterns import detect_candlesticks
from engine.risk_calc import pip_calculator
from services.notification_queue import format_confirmation_message


def test_confirmation_message_contains_complete_trade_information():
    payload = {
        "symbol": "EURUSD", "direction": "BUY_BIAS", "entry": 1.1,
        "stop_loss": 1.095, "take_profit": 1.11, "risk_reward": 2,
        "confidence": 0.78, "lot_size": 0.2, "position_size": 20000,
        "strategy": "both", "timeframe": "15min",
        "session": "London", "trend": "BULLISH", "confluence_score": 82,
        "confirmation_reason": "Bullish MSS confirmed",
    }
    message = format_confirmation_message(payload)
    for value in (
        "EURUSD", "BUY_BIAS", "1.095", "1.11", "0.78", "0.2", "20000",
        "both", "15min", "London", "BULLISH", "82", "Bullish MSS",
    ):
        assert value in message


def test_forex_and_gold_position_sizing():
    forex = pip_calculator("EURUSD", 1.1, 1.095, 1.11, balance=1000, risk_pct=1)
    gold = pip_calculator("XAUUSD", 2400, 2390, 2420, balance=10000, risk_pct=1)
    assert forex["requested_risk_amount"] == 10
    assert forex["position_size"] == forex["lot_size"] * 100000
    assert gold["contract_size"] == 100
    assert gold["position_size"] == gold["lot_size"] * 100


def test_pattern_detection_is_supporting_evidence():
    frame = pd.DataFrame([
        {"Open": 1.0, "High": 1.01, "Low": 0.99, "Close": 0.995},
        {"Open": 0.995, "High": 1.0, "Low": 0.98, "Close": 0.985},
        {"Open": 0.984, "High": 1.02, "Low": 0.983, "Close": 1.015},
    ])
    patterns = detect_candlesticks(frame)
    assert any(item["name"] == "Bullish Engulfing" for item in patterns)
    assert all(item["weight"] <= 0.35 for item in patterns)


def test_admin_logs_support_server_side_filters(client, admin_token, monkeypatch, tmp_path):
    from tests.helpers import auth
    import admin_panel

    log_file = tmp_path / "smartflow.log"
    log_file.write_text(
        "2026-07-26 10:00:00 | INFO     | smartflow.engine.pipeline | prediction ready\n"
        "2026-07-26 10:01:00 | ERROR    | smartflow.bot | telegram failed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(admin_panel, "LOG_FILE", str(log_file))
    response = client.get(
        "/admin/api/logs?severity=ERROR&source=telegram&search=failed",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    entries = response.get_json()["entries"]
    assert len(entries) == 1
    assert entries[0]["severity"] == "ERROR"
    assert entries[0]["source"] == "telegram"


def test_render_uses_separate_always_on_api_and_worker():
    text = __import__("pathlib").Path("render.yaml").read_text(encoding="utf-8")
    assert "type: web" in text
    assert "type: worker" in text
    assert "gunicorn --config deploy/gunicorn.conf.py app:app" in text
    assert "python run.py ai-worker" in text
    assert "python run.py scheduler" in text
    assert "healthCheckPath: /readyz" in text
