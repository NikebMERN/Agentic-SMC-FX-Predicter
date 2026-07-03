# tests/test_phase1.py
"""Phase 1: 4-state decide, verification, conflicts, compliance, kill switch."""
import pandas as pd
import pytest

from engine import confluence
from engine.confluence import ACTION_BUY, ACTION_NO_TRADE, ACTION_WAIT
from engine.signals_export import export_signals
from services.prediction_review import verify_candles, parse_horizon
from services.training_service import detect_conflict
from utils.compliance import assert_safe_wording, DISCLAIMER


def _base_analysis(zone="discount", position=0.2, with_structure=True):
    n = 50
    idx = pd.date_range("2025-01-06 03:00", periods=n, freq="h")
    close = [1.10 + i * 0.0001 for i in range(n)]
    df = pd.DataFrame(
        {"Open": close, "High": [c + 0.001 for c in close],
         "Low": [c - 0.001 for c in close], "Close": close, "Volume": 0.0},
        index=idx,
    )
    events = [{
        "kind": "BOS", "direction": "bullish", "pos": 40,
        "displacement": True, "level": 1.104,
    }] if with_structure else []
    return {
        "symbol": "EURUSD",
        "bars": n,
        "price": float(close[-1]),
        "atr": 0.001,
        "df": df,
        "swings": pd.DataFrame(columns=["pos", "kind", "price"]),
        "structure": {"events": events, "trend": 1},
        "valid_order_blocks": [{
            "direction": "bullish", "status": "fresh",
            "low": 1.101, "high": 1.102, "event_kind": "BOS",
        }] if with_structure else [],
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
        "htf_bias": {"direction": "bullish", "strength": 70, "confidence": 0.7, "interval": "240min", "reason": "HTF BOS"},
    }


def test_decide_includes_component_scores_and_disclaimer():
    decision = confluence.decide(_base_analysis())
    assert "component_scores" in decision
    assert decision["disclaimer"] == DISCLAIMER
    assert "htf_bias" in decision["component_scores"]
    assert decision["action"] in (ACTION_BUY, ACTION_NO_TRADE, ACTION_WAIT)


def test_wait_for_confirmation_on_forming_setup():
    analysis = _base_analysis(with_structure=False)
    analysis["valid_order_blocks"] = []
    analysis["htf_bias"] = None
    analysis["premium_discount"] = {"position": 0.75, "zone": "premium"}
    decision = confluence.decide(analysis)
    assert decision["action"] in (ACTION_WAIT, ACTION_NO_TRADE)
    if decision["action"] == ACTION_WAIT:
        assert decision.get("invalidation_price") is not None


def test_signal_export_structure():
    analysis = _base_analysis()
    signals = export_signals(analysis, interval="60min")
    assert signals
    sig = signals[0]
    for key in ("name", "framework", "direction", "strength", "validation_reason", "status"):
        assert key in sig


def test_verify_candles_invalidation_first():
    idx = pd.date_range("2025-01-01", periods=5, freq="h")
    candles = pd.DataFrame({
        "Open": [1.10, 1.10, 1.10, 1.10, 1.10],
        "High": [1.101, 1.101, 1.101, 1.101, 1.101],
        "Low": [1.099, 1.098, 1.097, 1.096, 1.095],
        "Close": [1.100, 1.099, 1.098, 1.097, 1.096],
    }, index=idx)
    result = verify_candles(
        candles,
        entry=1.10,
        invalidation=1.098,
        target=1.105,
        predicted_action="BUY_BIAS",
        atr=0.001,
    )
    assert result["invalidation_hit"] is True
    assert result["outcome"] == "AI_WRONG"


def test_verify_sideways_no_trade():
    idx = pd.date_range("2025-01-01", periods=3, freq="h")
    candles = pd.DataFrame({
        "Open": [1.10, 1.10, 1.10],
        "High": [1.1001, 1.1001, 1.1001],
        "Low": [1.0999, 1.0999, 1.0999],
        "Close": [1.10, 1.10, 1.10],
    }, index=idx)
    result = verify_candles(
        candles, entry=1.10, invalidation=None, target=None,
        predicted_action="NO_TRADE", atr=0.001,
    )
    assert result["actual_direction"] == "SIDEWAYS"
    assert result["outcome"] == "NO_TRADE_CONFIRMED"


def test_conflict_matrix():
    assert detect_conflict("SUCCESSFUL", "DOWN", "BUY_BIAS") is True
    assert detect_conflict("SUCCESSFUL", "UP", "BUY_BIAS") is False
    assert detect_conflict("FAILED", "UP", "BUY_BIAS") is True
    assert detect_conflict(None, "UP", "BUY_BIAS") is False


def test_compliance_scrubs_guaranteed():
    out = assert_safe_wording("This is a guaranteed win signal")
    assert "guaranteed" not in out.lower()


def test_horizon_parse():
    assert parse_horizon("scalping")[1] == 1
    assert parse_horizon("swing")[1] == 24
    assert parse_horizon("invalid")[0] == "intraday"
