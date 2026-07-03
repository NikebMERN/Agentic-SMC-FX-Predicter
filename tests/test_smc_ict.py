# tests/test_smc_ict.py
"""Unit tests for the valid-signal SMC and ICT detectors, on hand-built
candle patterns where the correct answer is known by construction."""
import numpy as np
import pandas as pd
import pytest

from engine import ict, smc


def make_df(highs, lows, opens, closes, start="2025-01-06 00:00"):
    idx = pd.date_range(start, periods=len(highs), freq="h")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": 0.0},
        index=pd.Index(idx, name="Timestamp"),
    )


# ---------------------------------------------------------------------
# FVG: correct 3-candle definition (the legacy detector had it inverted)
# ---------------------------------------------------------------------
def test_bullish_fvg_detected_with_correct_orientation():
    n = 20
    highs = [1.1002] * n
    lows = [1.0998] * n
    opens = [1.1000] * n
    closes = [1.1000] * n
    # candles 10/11/12: gap up — candle 10 high < candle 12 low
    highs[10], lows[10], opens[10], closes[10] = 1.1002, 1.0998, 1.1000, 1.1001
    highs[11], lows[11], opens[11], closes[11] = 1.1030, 1.1000, 1.1001, 1.1029  # displacement
    highs[12], lows[12], opens[12], closes[12] = 1.1032, 1.1012, 1.1029, 1.1030
    # keep later candles above the gap so it stays unfilled
    for i in range(13, n):
        highs[i], lows[i], opens[i], closes[i] = 1.1033, 1.1013, 1.1030, 1.1030

    df = make_df(highs, lows, opens, closes)
    gaps = smc.detect_fvg(df, smc.atr(df), require_displacement=False)

    bullish = [g for g in gaps if g["direction"] == "bullish"]
    assert len(bullish) == 1
    gap = bullish[0]
    assert gap["pos"] == 11  # the displacement (middle) candle
    assert gap["low"] == pytest.approx(1.1002)   # candle 10 high
    assert gap["high"] == pytest.approx(1.1012)  # candle 12 low


def test_fully_filled_fvg_is_discarded():
    n = 20
    highs = [1.1002] * n
    lows = [1.0998] * n
    opens = [1.1000] * n
    closes = [1.1000] * n
    highs[10], lows[10], opens[10], closes[10] = 1.1002, 1.0998, 1.1000, 1.1001
    highs[11], lows[11], opens[11], closes[11] = 1.1030, 1.1000, 1.1001, 1.1029
    highs[12], lows[12], opens[12], closes[12] = 1.1032, 1.1012, 1.1029, 1.1030
    # candle 15 trades all the way through the gap -> filled -> invalid
    highs[15], lows[15], opens[15], closes[15] = 1.1030, 1.1001, 1.1029, 1.1002

    df = make_df(highs, lows, opens, closes)
    gaps = smc.detect_fvg(df, smc.atr(df), require_displacement=False)
    assert [g for g in gaps if g["direction"] == "bullish"] == []


# ---------------------------------------------------------------------
# Structure: BOS requires a body close beyond the swing — wicks don't count
# ---------------------------------------------------------------------
def _structure_case():
    highs = [1.1000, 1.1000, 1.1005, 1.1050, 1.1010, 1.1008, 1.1060, 1.1070]
    lows = [1.0990] * 8
    opens = [1.0995, 1.0995, 1.0995, 1.0995, 1.0995, 1.1005, 1.0995, 1.1000]
    closes = [1.0995, 1.0995, 1.1000, 1.1000, 1.1000, 1.0995, 1.1000, 1.1070]
    return make_df(highs, lows, opens, closes)


def test_wick_poke_is_not_bos_but_body_close_is():
    df = _structure_case()
    swings = smc.find_swings(df, window=2)
    assert (swings["kind"] == "high").sum() == 1  # the 1.1050 swing high

    structure = smc.detect_structure(df, swings, window=2)
    events = structure["events"]
    # candle 6 wicked to 1.1060 (above 1.1050) but closed 1.1000 -> no event there
    assert all(ev["pos"] != 6 for ev in events)
    # candle 7 CLOSED at 1.1070 -> that is the break
    assert len(events) == 1
    assert events[0]["pos"] == 7
    assert events[0]["kind"] == "BOS"
    assert events[0]["direction"] == "bullish"
    assert structure["trend"] == 1


def test_order_block_lifecycle_fresh_then_invalidated():
    df = _structure_case()
    swings = smc.find_swings(df, window=2)
    structure = smc.detect_structure(df, swings, window=2)
    blocks = smc.detect_order_blocks(df, structure["events"])
    assert len(blocks) == 1
    ob = blocks[0]
    assert ob["direction"] == "bullish"
    assert ob["pos"] == 5  # last bearish candle before the impulse
    assert ob["status"] == "fresh"
    assert smc.valid_order_blocks(blocks) == blocks

    # extend history: price closes below the block -> invalidated -> not an entry zone
    df2 = pd.concat([df, make_df([1.0995], [1.0980], [1.0990], [1.0985],
                                 start=df.index[-1] + pd.Timedelta(hours=1))])
    blocks2 = smc.detect_order_blocks(df2, structure["events"])
    assert blocks2[0]["status"] == "invalidated"
    assert smc.valid_order_blocks(blocks2) == []


# ---------------------------------------------------------------------
# Liquidity: equal highs pool + valid sweep (wick through, close back)
# ---------------------------------------------------------------------
def _pool_case():
    highs = [1.1000, 1.1000, 1.1000, 1.1050, 1.1005, 1.1005,
             1.1000, 1.1000, 1.1000, 1.1050, 1.1005, 1.1005, 1.1056]
    lows = [1.0990] * 13
    opens = [1.0995] * 13
    closes = [1.0995] * 12 + [1.1000]  # sweep candle closes back under 1.1050
    return make_df(highs, lows, opens, closes)


def test_equal_highs_pool_and_bearish_sweep():
    df = _pool_case()
    swings = smc.find_swings(df, window=2)
    pools = smc.detect_liquidity_pools(df, swings, tolerance=0.0005)

    buyside = [p for p in pools if p["side"] == "buyside"]
    assert len(buyside) == 1
    pool = buyside[0]
    assert pool["level"] == pytest.approx(1.1050)
    assert pool["points"] == 2
    assert pool["swept"] and pool["sweep_rejected"]

    sweeps = ict.detect_sweeps(df, pools, swings, recent_bars=24)
    assert any(s["bias"] == "bearish" and s["pos"] == 12 for s in sweeps)


def test_accepted_breakout_is_not_a_sweep():
    df = _pool_case()
    # add a candle that CLOSES above the swept level -> market accepted it
    df2 = pd.concat([df, make_df([1.1080], [1.1040], [1.1050], [1.1075],
                                 start=df.index[-1] + pd.Timedelta(hours=1))])
    swings = smc.find_swings(df2, window=2)
    pools = smc.detect_liquidity_pools(df2, swings, tolerance=0.0005)
    sweeps = ict.detect_sweeps(df2, pools, swings, recent_bars=24)
    assert all(s["bias"] != "bearish" or s["level"] != pytest.approx(1.1050) for s in sweeps)


# ---------------------------------------------------------------------
# ICT: premium/discount, OTE, kill zones
# ---------------------------------------------------------------------
def test_premium_discount_zones():
    rng = {"low": 1.0, "high": 2.0, "direction": "bullish"}
    assert ict.premium_discount(1.10, rng)["zone"] == "discount"
    assert ict.premium_discount(1.50, rng)["zone"] == "equilibrium"
    assert ict.premium_discount(1.90, rng)["zone"] == "premium"
    assert ict.premium_discount(1.90, rng)["position"] == pytest.approx(0.9)


def test_ote_zone_is_618_to_79_retracement():
    rng = {"low": 1.0, "high": 2.0, "direction": "bullish"}
    ote = ict.ote_zone(rng)
    assert ote["low"] == pytest.approx(2.0 - 0.79)
    assert ote["high"] == pytest.approx(2.0 - 0.618)
    assert ict.price_in_zone(1.3, ote)
    assert not ict.price_in_zone(1.9, ote)
    assert ict.ote_zone({"low": 1.0, "high": 2.0, "direction": "neutral"}) is None


def test_killzones():
    assert ict.active_killzone(pd.Timestamp("2025-01-06 03:00")) == "London"
    assert ict.active_killzone(pd.Timestamp("2025-01-06 08:30")) == "NewYork"
    assert ict.active_killzone(pd.Timestamp("2025-01-06 20:00")) is None


def test_breaker_block_after_sweep():
    """Invalidated OB after liquidity sweep flips polarity."""
    df = make_df([1.1000] * 25, [1.0990] * 25, [1.0995] * 25, [1.0995] * 25)
    blocks = [{
        "direction": "bullish",
        "status": "invalidated",
        "invalidated_pos": 20,
        "low": 1.0990,
        "high": 1.1005,
        "pos": 4,
        "event_kind": "BOS",
    }]
    sweeps = [{"pos": 16, "side": "buyside", "level": 1.1060, "bias": "bearish"}]
    breakers = ict.detect_breakers(df, blocks, sweeps)
    assert len(breakers) == 1
    assert breakers[0]["direction"] == "bearish"
    assert breakers[0]["low"] == pytest.approx(1.0990)
