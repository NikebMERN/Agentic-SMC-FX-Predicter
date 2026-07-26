"""Historical-style scenario regressions for institutional rule priority."""
import pandas as pd

from engine.institutional import execution_confirmation
from engine.ml_gate import apply_ml_gate
from engine.smc import atr, detect_structure, find_swings


def _frame(rows):
    index = pd.date_range("2025-01-06", periods=len(rows), freq="15min")
    return pd.DataFrame(rows, index=index)


def test_weak_close_above_swing_is_rejected_as_fake_bos():
    closes = [1.1000, 1.1010, 1.1030, 1.1010, 1.1000, 1.1020, 1.1035, 1.1020, 1.1010]
    rows = []
    for close in closes:
        rows.append({
            "Open": close + 0.00005,
            "High": close + 0.0004,
            "Low": close - 0.0004,
            "Close": close,
            "Volume": 0,
        })
    frame = _frame(rows)
    swings = find_swings(frame, 1)
    structure = detect_structure(frame, swings, 1, atr(frame))
    assert any(item["reason"] == "weak or opposing break candle" for item in structure["rejected_breaks"])


def test_execution_requires_sweep_then_displaced_shift():
    analysis = {
        "bars": 100,
        "structure": {"events": [{
            "pos": 98, "kind": "MSS", "direction": "bullish", "displacement": True,
        }]},
        "sweeps": [{
            "pos": 96, "bias": "bullish", "side": "sellside",
            "level": 1.09, "bars_ago": 3,
        }],
    }
    assert execution_confirmation(analysis, "bullish")["confirmed"]
    analysis["sweeps"][0]["pos"] = 99
    result = execution_confirmation(analysis, "bullish")
    assert not result["confirmed"]
    assert any("after" in reason for reason in result["reasons"])


def test_continuation_bos_is_not_entry_confirmation():
    analysis = {
        "bars": 100,
        "structure": {"events": [{
            "pos": 98, "kind": "BOS", "direction": "bullish", "displacement": True,
        }]},
        "sweeps": [{
            "pos": 96, "bias": "bullish", "side": "sellside",
            "level": 1.09, "bars_ago": 3,
        }],
    }
    result = execution_confirmation(analysis, "bullish")
    assert not result["confirmed"]
    assert any("Continuation BOS" in reason for reason in result["reasons"])


def test_ml_only_adjusts_confidence_not_rule_truth():
    decision = {
        "action": "BUY_BIAS", "confidence": 0.82, "rule_confidence": 0.82,
        "reasoning": [], "vetoes": [],
    }
    result = apply_ml_gate(decision, ml_probability=0.05, has_active_model=True)
    assert result["action"] == "BUY_BIAS"
    assert result["confidence"] < decision["confidence"]
