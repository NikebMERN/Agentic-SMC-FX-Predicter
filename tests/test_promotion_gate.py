"""Tests for promotion gate."""
from ml.promotion_gate import DEFAULT_GATE, evaluate_promotion, get_promotion_gate


def test_promotion_gate_defaults():
    gate = get_promotion_gate()
    assert gate["min_f1"] == DEFAULT_GATE["min_f1"]


def test_promotion_passes_strong_candidate():
    candidate = {
        "walk_forward_score": 0.55,
        "precision": 0.6,
        "f1": 0.5,
        "brier_score": 0.2,
        "samples": 100,
    }
    result = evaluate_promotion(candidate, None, gate={**DEFAULT_GATE, "min_samples": 50})
    assert result["passed"] is False  # feature flag off by default


def test_promotion_rejects_weak_candidate():
    candidate = {"walk_forward_score": 0.2, "precision": 0.3, "f1": 0.2, "brier_score": 0.4, "samples": 10}
    result = evaluate_promotion(candidate, None)
    assert result["passed"] is False
    assert result["reasons"]
