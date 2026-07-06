# tests/test_topdown_predict.py
"""Integration tests for top-down prediction flow."""
from engine.data import from_oanda_instrument, to_display_pair, to_oanda_instrument
from engine.prediction_response import build_prediction_response
from engine.trading_style import all_timeframes, normalize_trading_style


def test_pair_conversion():
    assert to_oanda_instrument("EURUSD") == "EUR_USD"
    assert to_display_pair("EUR_USD") == "EUR/USD"
    assert from_oanda_instrument("GBP_USD") == "GBPUSD"


def test_trading_style_ladders():
    assert normalize_trading_style("scalp") == "scalping"
    assert "240min" in all_timeframes("intraday")
    assert "daily" in all_timeframes("swing")


def test_prediction_response_schema():
    decision = {
        "action": "NO_TRADE",
        "confidence": 0.0,
        "score": 30,
        "reasoning": ["No setup"],
        "invalid_reasons": ["Insufficient confluence"],
        "market_trend": "RANGING",
    }
    analysis = {
        "structure": {"events": [], "trend": 0},
        "pools": [],
        "sweeps": [],
        "fvgs": [],
        "valid_order_blocks": [],
        "premium_discount": {"zone": "equilibrium", "position": 0.5},
        "dealing_range": {"low": 1.09, "high": 1.11},
    }
    resp = build_prediction_response("EURUSD", "intraday", decision, analysis)
    assert resp["pair"] == "EUR/USD"
    assert resp["oandaInstrument"] == "EUR_USD"
    assert resp["direction"] == "NO_TRADE"
    assert resp["modelVersion"] == "smc-ict-v1"
    assert "riskWarning" in resp
    assert resp["entryPlan"]["invalidationPrice"] is None


def test_predict_symbol_returns_prediction_object(synthetic_csv, initialized_db):
    from engine.pipeline import predict_symbol
    result = predict_symbol("TSTUSD", fetch=False, trading_style="intraday")
    assert "prediction" in result
    assert result["prediction"]["tradingStyle"] == "intraday"
    assert result["prediction"]["direction"] in (
        "BUY_BIAS", "SELL_BIAS", "WAIT_FOR_CONFIRMATION", "NO_TRADE"
    )
