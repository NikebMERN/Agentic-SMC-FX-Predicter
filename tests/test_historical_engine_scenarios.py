"""Invariant checks on repository historical candle scenarios."""
from pathlib import Path

import pandas as pd
import pytest

from config.smc_ict_thresholds import DEFAULT_THRESHOLDS
from engine.confluence import analyze, decide, is_trade_action
from engine.data import load_ohlc_csv
from schemas.threshold_schema import min_risk_reward_for_style, validate_threshold_config


HISTORICAL_EURUSD = Path("data/EURUSD_15min.csv")


@pytest.mark.skipif(not HISTORICAL_EURUSD.exists(), reason="historical EURUSD fixture unavailable")
def test_historical_trade_requires_institutional_confirmation_and_safe_risk():
    frame = load_ohlc_csv(str(HISTORICAL_EURUSD)).tail(900)
    assert len(frame) >= 200
    thresholds = validate_threshold_config(DEFAULT_THRESHOLDS)
    analysis = analyze(
        frame, "EURUSD", interval="15min",
        thresholds=thresholds, trading_style="intraday",
    )
    decision = decide(
        analysis, strategy_mode="both",
        thresholds=thresholds, spread_ok=True, data_valid=True,
    )
    assert decision["action"] in {
        "BUY_BIAS", "SELL_BIAS", "WAIT_FOR_CONFIRMATION", "NO_TRADE",
    }
    if is_trade_action(decision["action"]):
        confirmation = decision["institutional_confirmation"]
        assert confirmation["confirmed"]
        assert decision["risk_reward"] >= min_risk_reward_for_style(thresholds, "intraday")
        assert not decision["stop_exceeds_cap"]
        assert decision["stop_basis"] == "structure"
    else:
        assert decision["no_trade_reasons"] or decision["vetoes"] or decision["action"] == "WAIT_FOR_CONFIRMATION"
