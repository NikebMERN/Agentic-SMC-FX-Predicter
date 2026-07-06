# tests/test_scoring.py
"""Scoring engine and NO_TRADE gate tests."""
import pandas as pd

from engine.confluence import ACTION_NO_TRADE, ACTION_WAIT, decide
from engine.scoring import compute_decision


def _base_analysis(**overrides):
    base = {
        "symbol": "EURUSD",
        "trading_style": "intraday",
        "bars": 500,
        "price": 1.1000,
        "atr": 0.0010,
        "swings": pd.DataFrame(columns=["pos", "kind", "price"]),
        "structure": {"events": [], "trend": 0},
        "valid_order_blocks": [],
        "fvgs": [],
        "pools": [],
        "sweeps": [],
        "premium_discount": {"zone": "equilibrium", "position": 0.5},
        "killzone": None,
        "session": {"active": None, "weight": 0.35},
        "ote": None,
        "breakers": [],
        "htf_bias": {"direction": "neutral", "bias_label": "NEUTRAL"},
        "higher_timeframe_bias": "NEUTRAL",
        "execution_confirmed": False,
    }
    base.update(overrides)
    return base


def test_no_trade_when_score_too_low():
    analysis = _base_analysis()
    d = compute_decision(analysis, data_valid=True, spread_ok=True)
    assert d["action"] in (ACTION_NO_TRADE, ACTION_WAIT)
    assert d["score"] < 60


def test_no_trade_when_data_invalid():
    analysis = _base_analysis(
        sweeps=[{"bias": "bullish", "side": "sellside", "level": 1.098, "bars_ago": 2}],
        structure={"events": [{"kind": "CHoCH", "direction": "bullish", "displacement": True, "level": 1.101, "pos": 400}], "trend": 1},
        premium_discount={"zone": "discount", "position": 0.3},
    )
    d = compute_decision(analysis, data_valid=False, spread_ok=True)
    assert d["action"] == ACTION_NO_TRADE


def test_htf_conflict_blocks_bias():
    analysis = _base_analysis(
        htf_conflict={"conflict": True, "reason": "4H bearish vs 1H bullish"},
        htf_bias={"direction": "bearish", "bias_label": "BEARISH"},
        higher_timeframe_bias="BEARISH",
    )
    d = compute_decision(analysis, data_valid=True, spread_ok=True)
    assert d["action"] in (ACTION_NO_TRADE, ACTION_WAIT)


def test_decide_delegates_to_scoring():
    analysis = _base_analysis()
    d = decide(analysis, data_valid=True, spread_ok=True)
    assert "score" in d
    assert "invalid_reasons" in d or "no_trade_reasons" in d
