# tests/test_thresholds.py
"""Threshold merge and pair override tests."""
import pytest

from utils.thresholds import DEFAULT_THRESHOLDS, get_thresholds, save_global_thresholds, invalidate_cache


def test_defaults_present():
    t = get_thresholds("EURUSD")
    for key in DEFAULT_THRESHOLDS:
        assert key in t


@pytest.mark.usefixtures("initialized_db")
def test_global_override_merge():
    from services.threshold_service import seed_initial_version
    seed_initial_version()
    invalidate_cache()
    merged = save_global_thresholds({"minScoreForWait": 45})
    assert merged["minScoreForWait"] == 45
    assert merged["minFvgSizePips"] == DEFAULT_THRESHOLDS["minFvgSizePips"]
    invalidate_cache()
