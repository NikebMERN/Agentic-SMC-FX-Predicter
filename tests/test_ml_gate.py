"""Tests for ML quality gate."""
from engine.confluence import ACTION_BUY
from engine.ml_gate import apply_ml_gate


def test_ml_gate_no_model_caps_confidence():
    decision = {"action": ACTION_BUY, "rule_confidence": 0.9, "confidence": 0.9, "reasoning": [], "vetoes": []}
    out = apply_ml_gate(decision, ml_probability=None, has_active_model=False)
    assert out["confidence"] <= 0.70


def test_ml_gate_cannot_downgrade_rule_action_to_wait():
    decision = {"action": ACTION_BUY, "rule_confidence": 0.75, "confidence": 0.75, "reasoning": [], "vetoes": []}
    out = apply_ml_gate(decision, ml_probability=0.55, has_active_model=True)
    assert out["action"] == ACTION_BUY
    assert out["confidence"] <= 0.60


def test_ml_gate_cannot_override_rule_action_with_no_trade():
    decision = {"action": ACTION_BUY, "rule_confidence": 0.75, "confidence": 0.75, "reasoning": [], "vetoes": []}
    out = apply_ml_gate(decision, ml_probability=0.45, has_active_model=True)
    assert out["action"] == ACTION_BUY
    assert out["confidence"] <= 0.50
