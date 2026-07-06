# tests/test_mtf_and_calc.py
"""Multi-timeframe stack (4H bias -> 1H liquidity -> 30min entry) and the
automated pip / position calculator."""
import pandas as pd
import pytest

from engine.mtf import _frame_minutes, _pick_draw, _resample_4h, mtf_analyze
from engine.risk_calc import pip_calculator


# ---------------------------------------------------------------------
# pip calculator
# ---------------------------------------------------------------------
def test_calculator_usd_quote_exact_math():
    calc = pip_calculator(
        "EURUSD", entry=1.1000, stop_loss=1.0980, take_profit=1.1040,
        balance=1000, risk_pct=1.0,
    )
    assert calc["sl_pips"] == pytest.approx(20.0)
    assert calc["tp_pips"] == pytest.approx(40.0)
    assert calc["pip_value_per_lot_usd"] == pytest.approx(10.0)
    assert calc["lot_size"] == pytest.approx(0.05)   # $10 risk / (20 pips * $10)
    assert calc["risk_amount"] == pytest.approx(10.0)
    assert calc["reward_amount"] == pytest.approx(20.0)
    assert calc["risk_reward"] == pytest.approx(2.0)
    assert calc["approximate"] is False


def test_calculator_jpy_pair_uses_conversion():
    calc = pip_calculator(
        "USDJPY", entry=150.00, stop_loss=150.30, take_profit=149.40,
        balance=2000, risk_pct=2.0,
    )
    assert calc["sl_pips"] == pytest.approx(30.0)
    assert calc["tp_pips"] == pytest.approx(60.0)
    assert calc["risk_reward"] == pytest.approx(2.0)
    # pip value converts 1000 JPY through the cached USDJPY rate (~$6-8)
    assert 4.0 < calc["pip_value_per_lot_usd"] < 12.0
    assert calc["risk_amount"] <= 2000 * 0.02 + 1  # never risks more than asked


def test_calculator_rejects_zero_stop_distance():
    with pytest.raises(ValueError):
        pip_calculator("EURUSD", 1.1, 1.1, 1.12)


def test_calculator_never_risks_more_than_requested():
    # exact lot would be 0.0185; the OLD round() gave 0.02 = $4.00 risk
    # (over the requested $3.70). Floor must keep actual risk <= requested.
    calc = pip_calculator(
        "EURUSD", entry=1.1000, stop_loss=1.0980, take_profit=1.1040,
        balance=1000, risk_pct=0.37,
    )
    assert calc["requested_risk_amount"] == pytest.approx(3.70)
    assert calc["lot_size"] == pytest.approx(0.01)
    assert calc["risk_amount"] <= calc["requested_risk_amount"]
    assert calc["risk_exceeds_requested"] is False


def test_calculator_fixed_risk_amount_overrides_percent():
    calc = pip_calculator(
        "EURUSD", entry=1.1000, stop_loss=1.0980, take_profit=1.1040,
        balance=50000, risk_pct=5.0, risk_amount=25.0,
    )
    assert calc["requested_risk_amount"] == pytest.approx(25.0)
    assert calc["risk_amount"] <= 25.0
    assert calc["lot_size"] == pytest.approx(0.12)  # floor(25/(20*10)*100)/100


def test_calculator_warns_when_min_lot_exceeds_requested_risk():
    # $20 balance at 1% = $0.20 requested, but 0.01 lots on a 20-pip stop
    # risks $2.00 — the user must be warned, never silently over-risked.
    calc = pip_calculator(
        "EURUSD", entry=1.1000, stop_loss=1.0980, take_profit=1.1040,
        balance=20, risk_pct=1.0,
    )
    assert calc["lot_size"] == pytest.approx(0.01)
    assert calc["risk_exceeds_requested"] is True
    assert calc["warning"]


def test_telegram_text_shows_levels_and_calculator_for_wait():
    from engine.pipeline import format_result_text
    result = {
        "symbol": "EURUSD",
        "strategy": "both",
        "candles": 500,
        "data_source": "oanda",
        "last_candle": "2026-07-03 12:00:00",
        "mtf": {
            "timeframes": {"bias": "240min", "liquidity": "60min", "entry": "30min"},
            "h1_liquidity": {"above": [{}], "below": []},
            "liquidity_draw": {"level": 1.1465, "pips_away": 27.2},
        },
        "calculator": {
            "balance": 1000, "risk_pct": 1.0, "lot_size": 0.37,
            "risk_amount": 9.99, "reward_amount": 68.82,
            "pip_value_per_lot_usd": 10.0, "sl_pips": 2.7, "tp_pips": 18.6,
            "approximate": False, "warning": None,
        },
        "decision": {
            "action": "WAIT_FOR_CONFIRMATION",
            "confidence": 0.54, "rule_confidence": 0.6, "ml_confidence": None,
            "scores": {"bullish": 5.0, "bearish": 2.0}, "confluences": 3,
            "entry": 1.14386, "stop_loss": 1.14359, "take_profit": 1.14572,
            "invalidation_price": 1.14359, "target_liquidity": 1.14572,
            "risk_reward": 6.89, "sl_pips": 2.7, "sl_pct": 0.024,
            "tp_pips": 18.6, "tp_pct": 0.163,
            "killzone": None, "reasoning": ["test"], "vetoes": [],
        },
    }
    text = format_result_text(result)
    assert "Stop Loss: 1.14359" in text
    assert "Take Profit: 1.14572" in text
    assert "Position calculator" in text
    assert "Lot size: 0.37" in text
    assert "Draw on liquidity" in text


# ---------------------------------------------------------------------
# multi-timeframe stack
# ---------------------------------------------------------------------
def test_resample_4h(synthetic_ohlc):
    df4 = _resample_4h(synthetic_ohlc)
    assert len(df4) <= len(synthetic_ohlc) // 3
    # a 4H candle's high is the max of its 1H components
    first_window = synthetic_ohlc.iloc[:4]
    assert df4["High"].iloc[0] == pytest.approx(first_window["High"].max())
    assert _frame_minutes(df4) == pytest.approx(240.0)


def test_pick_draw_prefers_nearest_reachable_pool():
    liquidity = {
        "above": [
            {"level": 1.1050, "side": "buyside", "points": 2, "pips_away": 50.0},
            {"level": 1.1500, "side": "buyside", "points": 3, "pips_away": 500.0},
        ],
        "below": [],
    }
    draw = _pick_draw(liquidity, "bullish", price=1.1000)
    assert draw is not None
    assert draw["level"] == pytest.approx(1.1050)
    # a pool 500 pips away (>1.5% of price) is never the draw
    far_only = {"above": [liquidity["above"][1]], "below": []}
    assert _pick_draw(far_only, "bullish", price=1.1000) is None


def test_mtf_analyze_degrades_gracefully_on_cache_only(synthetic_csv):
    stack = mtf_analyze("TSTUSD", fetch=False, trading_style="intraday")
    ctx = stack["context"]
    assert stack["entry_tf"] in ("30min", "60min", "15min")
    assert any("fell back" in n or "unavailable" in n for n in ctx.get("notes", [])) or ctx.get("parent_biases")
    assert ctx.get("parent_biases") or ctx.get("h4_bias") is not None
    assert stack["analysis"]["bars"] > 100


def test_predict_symbol_defaults_to_mtf_with_calculator(synthetic_csv, initialized_db):
    from engine.pipeline import predict_symbol
    result = predict_symbol("TSTUSD", fetch=False)
    assert result["mtf"] is not None
    assert result.get("prediction") is not None
    assert "trading_style" in result
    d = result["decision"]
    if d.get("entry"):
        calc = result["calculator"]
        assert calc is not None
        assert calc["lot_size"] >= 0.01
        assert calc["risk_reward"] > 0
    single = predict_symbol("TSTUSD", interval="60min", fetch=False, mtf=False)
    assert single["mtf"] is None
