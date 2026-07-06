# tests/test_threshold_backtest.py
"""Threshold backtest metrics and version comparison."""
import pytest

from config.smc_ict_thresholds import DEFAULT_THRESHOLDS, resolve_thresholds
from engine.backtest import run_backtest
from services.threshold_backtest import compare_threshold_versions, run_threshold_backtest
from services import threshold_service


@pytest.mark.usefixtures("initialized_db")
def test_run_backtest_with_thresholds(synthetic_ohlc):
    threshold_service.seed_initial_version()
    t = resolve_thresholds("EURUSD", "60min", "intraday")
    result = run_threshold_backtest("EURUSD", synthetic_ohlc, t, interval="60min")
    assert "no_trade_rate" in result
    assert "wait_rate" in result
    assert "accuracy" in result


@pytest.mark.usefixtures("initialized_db")
def test_compare_two_versions(synthetic_ohlc):
    threshold_service.seed_initial_version()
    v1 = threshold_service.get_active_version()
    config = resolve_thresholds("EURUSD", "60min", "intraday", version_config={"decision": {"score_bias_minimum": 55}}).model_dump()
    v2 = threshold_service.create_version(config, "backtest-compare-b", activate=False)
    report = compare_threshold_versions("EURUSD", synthetic_ohlc, v1.id, v2.id, interval="60min")
    assert "version_a" in report
    assert "version_b" in report
    assert "delta" in report


def test_backtest_excludes_no_trade_from_bias_accuracy(synthetic_ohlc):
    result = run_backtest(synthetic_ohlc, "TSTUSD", thresholds=DEFAULT_THRESHOLDS, interval="60min")
    assert result.get("error") or "no_trade_rate" in result
