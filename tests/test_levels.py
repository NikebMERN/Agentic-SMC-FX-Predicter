# tests/test_levels.py
"""SL/TP realism: structure-based placement capped at a percent of price
so levels are actually reachable on the chart."""
import pandas as pd

from engine.confluence import (
    SL_MAX_PCT_DEFAULT,
    TP_MAX_PCT_DEFAULT,
    _stop_and_target,
)

PRICE = 1.1000
ATR = 0.0010  # 10 pips


def _analysis(obs=None, pools=None):
    return {
        "symbol": "EURUSD",
        "bars": 200,
        "price": PRICE,
        "atr": ATR,
        "valid_order_blocks": obs or [],
        "sweeps": [],
        "pools": pools or [],
        "swings": pd.DataFrame(columns=["pos", "time", "kind", "price"]),
    }


def test_far_structure_stop_is_capped_to_percent():
    # protective order block 2% below price — unrealistically far
    a = _analysis(obs=[{"direction": "bullish", "low": 1.0780, "high": 1.0800}])
    levels = _stop_and_target(a, "bullish", 5)
    max_dist = PRICE * SL_MAX_PCT_DEFAULT / 100
    assert PRICE - levels["stop_loss"] <= max_dist + 1e-9
    assert levels["stop_basis"] == "percent_cap"
    assert levels["sl_pips"] is not None and levels["sl_pct"] <= SL_MAX_PCT_DEFAULT + 1e-6


def test_faraway_liquidity_is_never_the_target():
    # only liquidity pool sits 5% above price — must not be suggested
    a = _analysis(pools=[{"side": "buyside", "swept": False, "level": 1.1550}])
    levels = _stop_and_target(a, "bullish", 5)
    tp_dist = levels["take_profit"] - PRICE
    assert tp_dist <= PRICE * TP_MAX_PCT_DEFAULT / 100 + 1e-9
    assert levels["target_basis"] == "risk_multiple"
    assert levels["tp_pct"] <= TP_MAX_PCT_DEFAULT + 1e-6


def test_nearby_structure_is_respected():
    # protector 15 pips below price — realistic, keep the structural stop
    a = _analysis(obs=[{"direction": "bullish", "low": 1.0985, "high": 1.0990}])
    levels = _stop_and_target(a, "bullish", 5)
    assert levels["stop_basis"] == "structure"
    assert levels["sl_pips"] < 25
    assert levels["stop_loss"] < PRICE < levels["take_profit"]


def test_bearish_levels_are_mirrored_and_capped():
    a = _analysis(obs=[{"direction": "bearish", "low": 1.1200, "high": 1.1250}])  # 2%+ above
    levels = _stop_and_target(a, "bearish", 5)
    assert levels["stop_loss"] > PRICE > levels["take_profit"]
    assert levels["sl_pct"] <= SL_MAX_PCT_DEFAULT + 1e-6
    assert levels["tp_pct"] <= TP_MAX_PCT_DEFAULT + 1e-6
