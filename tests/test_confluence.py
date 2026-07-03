# tests/test_confluence.py
"""Unit tests for confluence aggregation and veto rules."""
import pandas as pd
import pytest

from engine import confluence


def _base_analysis(zone="discount", position=0.2):
    n = 50
    idx = pd.date_range("2025-01-06 03:00", periods=n, freq="h")
    close = [1.10 + i * 0.0001 for i in range(n)]
    df = pd.DataFrame(
        {"Open": close, "High": [c + 0.001 for c in close],
         "Low": [c - 0.001 for c in close], "Close": close, "Volume": 0.0},
        index=idx,
    )
    return {
        "symbol": "EURUSD",
        "bars": n,
        "price": float(close[-1]),
        "atr": 0.001,
        "df": df,
        "swings": pd.DataFrame(columns=["pos", "kind", "price"]),
        "structure": {
            "events": [{
                "kind": "BOS", "direction": "bullish", "pos": 40,
                "displacement": True, "level": 1.104,
            }],
            "trend": 1,
        },
        "valid_order_blocks": [{
            "direction": "bullish", "status": "fresh",
            "low": 1.101, "high": 1.102, "event_kind": "BOS",
        }],
        "fvgs": [],
        "pools": [],
        "sweeps": [{
            "bias": "bullish", "side": "sellside", "level": 1.099,
            "bars_ago": 2, "pos": 47,
        }],
        "dealing_range": {"low": 1.0, "high": 2.0, "direction": "bullish"},
        "premium_discount": {"position": position, "zone": zone},
        "ote": None,
        "breakers": [],
        "killzone": "London",
    }


def test_bullish_in_premium_vetoed():
    decision = confluence.decide(_base_analysis(zone="premium", position=0.9))
    assert decision["action"] == "NO_TRADE"
    assert any("longs only valid in discount" in v for v in decision["vetoes"])


def test_bearish_in_discount_vetoed():
    analysis = _base_analysis(zone="discount", position=0.15)
    analysis["structure"]["events"] = [{
        "kind": "BOS", "direction": "bearish", "pos": 40,
        "displacement": True, "level": 1.102,
    }]
    analysis["valid_order_blocks"] = [{
        "direction": "bearish", "status": "fresh",
        "low": 1.108, "high": 1.109, "event_kind": "BOS",
    }]
    analysis["sweeps"] = [{
        "bias": "bearish", "side": "buyside", "level": 1.112,
        "bars_ago": 1, "pos": 48,
    }]
    decision = confluence.decide(analysis)
    assert decision["action"] == "NO_TRADE"
    assert any("shorts only valid in premium" in v for v in decision["vetoes"])
