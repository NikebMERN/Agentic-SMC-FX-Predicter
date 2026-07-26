from datetime import datetime

import numpy as np
import pandas as pd


def _frame(rows, frequency="h"):
    index = pd.date_range(datetime.utcnow(), periods=len(rows), freq=frequency)
    return pd.DataFrame(rows, index=pd.Index(index, name="Timestamp"))


def test_candle_validation_reports_ohlc_duplicates_gaps_and_outliers():
    from engine.candle_validator import validate_candles

    count = 60
    close = np.full(count, 1.10)
    close[-1] = 1.30
    frame = pd.DataFrame({
        "Open": np.full(count, 1.10),
        "High": np.full(count, 1.11),
        "Low": np.full(count, 1.09),
        "Close": close,
        "Volume": np.ones(count),
    }, index=pd.date_range(datetime.utcnow(), periods=count, freq="h"))
    frame.iloc[5, frame.columns.get_loc("High")] = 1.08
    frame.index = frame.index.to_list()[:-1] + [frame.index[-2]]

    result = validate_candles(frame, "EURUSD", "60min")
    assert result["valid"] is False
    assert result["quality"]["duplicate_count"] == 1
    assert result["quality"]["abnormal_movement_count"] >= 1
    assert any("invalid highs" in error for error in result["errors"])


def test_missing_timeframe_resamples_valid_cached_candles(monkeypatch, tmp_path):
    import engine.data as market_data

    index = pd.date_range("2026-01-01", periods=120, freq="15min")
    base = np.linspace(1.10, 1.12, len(index))
    frame = pd.DataFrame({
        "Open": base,
        "High": base + 0.0005,
        "Low": base - 0.0005,
        "Close": base + 0.0001,
        "Volume": 1.0,
    }, index=pd.Index(index, name="Timestamp"))
    monkeypatch.setattr(market_data, "DATA_DIR", str(tmp_path))
    frame.to_csv(market_data.csv_path("EURUSD", "15min"))
    monkeypatch.setattr(market_data, "_provider_chain", lambda: [])

    result, source = market_data.get_data("EURUSD", "60min", fetch=True)
    assert source == "resampled_cache"
    assert len(result) == 30
    diagnostics = market_data.get_last_data_diagnostics()
    assert diagnostics["fallback_used"] is True
    assert diagnostics["fallback_from"] == "15min"


def test_complete_candlestick_families_are_detected():
    from engine.patterns import detect_candlesticks

    soldiers = _frame([
        {"Open": 1.00, "High": 1.06, "Low": 0.99, "Close": 1.05, "Volume": 10},
        {"Open": 1.04, "High": 1.11, "Low": 1.03, "Close": 1.10, "Volume": 12},
        {"Open": 1.09, "High": 1.16, "Low": 1.08, "Close": 1.15, "Volume": 14},
    ])
    assert "Three Soldiers" in {item["name"] for item in detect_candlesticks(soldiers)}

    crows = _frame([
        {"Open": 1.15, "High": 1.16, "Low": 1.09, "Close": 1.10, "Volume": 10},
        {"Open": 1.11, "High": 1.12, "Low": 1.04, "Close": 1.05, "Volume": 12},
        {"Open": 1.06, "High": 1.07, "Low": 0.99, "Close": 1.00, "Volume": 14},
    ])
    assert "Three Crows" in {item["name"] for item in detect_candlesticks(crows)}


def test_patterns_cannot_create_or_reverse_institutional_direction():
    from engine.confluence import _collect_votes

    analysis = {
        "bars": 100,
        "price": 1.1,
        "atr": 0.001,
        "htf_bias": {},
        "liquidity_draw": {},
        "structure": {"events": []},
        "sweeps": [],
        "valid_order_blocks": [],
        "fvgs": [],
        "premium_discount": {"zone": "equilibrium", "position": 0.5},
        "ote": None,
        "breakers": [],
        "patterns": {
            "candlesticks": [{"name": "Hammer", "direction": "bullish", "weight": 0.30}],
            "chart_structures": [{"name": "Double Bottom", "direction": "bullish", "weight": 0.30}],
            "wyckoff": [{"name": "Wyckoff Spring", "direction": "bullish", "weight": 0.30}],
        },
        "killzone": None,
    }
    assert _collect_votes(analysis, "both") == []

    analysis["structure"]["events"] = [{
        "pos": 99, "kind": "BOS", "direction": "bearish",
        "displacement": True, "level": 1.11,
    }]
    votes = _collect_votes(analysis, "smc")
    assert all(direction != "bullish" for direction, _, _, _ in votes)
    support = sum(weight for _, weight, reason, _ in votes if "Supporting" in reason)
    assert support <= 0.50
