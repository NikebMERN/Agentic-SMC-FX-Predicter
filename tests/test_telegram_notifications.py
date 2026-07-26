from unittest.mock import Mock

import pytest


def test_lot_command_parser_accepts_forex_gold_and_percent(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "get_supported_pairs", lambda: ["EURUSD"])
    assert bot.parse_lot_command_args(["EURUSD", "1,000", "1%"]) == ("EURUSD", 1000.0, 1.0)
    assert bot.parse_lot_command_args(["XAUUSD", "5000", "0.5%"]) == ("XAUUSD", 5000.0, 0.5)


@pytest.mark.parametrize("args, message", [
    ([], "Usage"),
    (["BAD", "1000", "1%"], "Invalid currency pair"),
    (["AUDCAD", "1000", "1%"], "Unsupported symbol"),
    (["EURUSD", "0", "1%"], "Balance"),
    (["EURUSD", "1000", "0%"], "Risk percentage"),
    (["EURUSD", "1000", "11%"], "Risk percentage"),
])
def test_lot_command_parser_rejects_invalid_inputs(monkeypatch, args, message):
    import bot

    monkeypatch.setattr(bot, "get_supported_pairs", lambda: ["EURUSD"])
    with pytest.raises(ValueError, match=message):
        bot.parse_lot_command_args(args)


def test_telegram_http_retries_transient_server_failure(monkeypatch):
    import services.notifier as notifier

    monkeypatch.setattr(notifier, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(notifier.time, "sleep", lambda _seconds: None)
    failed = Mock(ok=False, status_code=503, text="temporary")
    delivered = Mock(ok=True, status_code=200, text="ok")
    delivered.json.return_value = {"result": {"message_id": 42}}
    post = Mock(side_effect=[failed, delivered])
    monkeypatch.setattr(notifier.requests, "post", post)

    assert notifier.send_message("123", "confirmation") is True
    assert post.call_count == 2


def test_signal_message_contains_complete_operational_fields():
    from engine.pipeline import format_result_text

    result = {
        "symbol": "EURUSD",
        "interval": "15min",
        "strategy": "ict",
        "mtf": None,
        "candles": 100,
        "data_source": "cache",
        "last_candle": "2026-01-01",
        "analysis_summary": {"killzone": "London", "trend": "BULLISH"},
        "calculator": {"lot_size": 0.12, "position_size": 12000},
        "decision": {
            "action": "BUY_BIAS", "direction": "bullish",
            "entry": 1.10, "stop_loss": 1.095, "take_profit": 1.11,
            "risk_reward": 2.0, "confidence": 0.78, "rule_confidence": 0.75,
            "ml_confidence": 0.70, "strategy": "ict", "score": 82,
            "scores": {"bullish": 7, "bearish": 1}, "confluences": 4,
            "reasoning": ["MSS confirmation after liquidity sweep"],
            "vetoes": [], "killzone": "London", "market_trend": "BULLISH",
            "institutional_confirmation": {
                "confirmed": True,
                "reasons": ["MSS confirmation after liquidity sweep"],
            },
            "sl_pips": 50, "sl_pct": 0.45, "tp_pips": 100, "tp_pct": 0.9,
            "disclaimer": "Not financial advice.",
        },
    }
    message = format_result_text(result)
    for label in (
        "Pair:", "Direction:", "Entry:", "Stop Loss:", "Take Profit:",
        "Risk Reward:", "Confidence:", "Lot Size:", "Position Size:",
        "Strategy:", "Timeframe:", "Session:", "Trend:",
        "Confluence Score:", "Confirmation reason:",
    ):
        assert label in message
