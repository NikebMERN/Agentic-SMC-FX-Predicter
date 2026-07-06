# tests/test_threshold_schema.py
"""Pydantic threshold schema validation."""
import pytest

from schemas.threshold_schema import (
    SmcIctThresholds,
    ThresholdValidationError,
    merge_threshold_patch,
    validate_threshold_config,
)
from config.smc_ict_thresholds import DEFAULT_THRESHOLDS


def test_defaults_valid():
    t = SmcIctThresholds()
    assert t.data_quality.min_candles_required == 200
    assert DEFAULT_THRESHOLDS.data_quality.min_candles_required == 200


def test_invalid_min_candles_rejected():
    with pytest.raises(ThresholdValidationError):
        validate_threshold_config({"data_quality": {"min_candles_required": 50}})


def test_patch_merge():
    base = SmcIctThresholds()
    patched = merge_threshold_patch(base, {"decision": {"score_bias_minimum": 65}})
    assert patched.decision.score_bias_minimum == 65
    assert patched.data_quality.min_candles_required == 200


def test_training_weights_must_sum_to_one():
    with pytest.raises(ThresholdValidationError):
        validate_threshold_config({
            "training": {"user_feedback_weight": 0.4, "market_verification_weight": 0.4},
        })
