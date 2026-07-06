# tests/test_structure_events.py
"""BOS, CHOCH, MSS detection tests."""
import numpy as np
import pandas as pd

from engine.smc import detect_mss, detect_structure, find_swings, atr


def _df_from_closes(closes, spread=0.0005):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="h")
    o = np.array(closes) - spread / 2
    c = np.array(closes) + spread / 2
    h = np.maximum(o, c) + spread
    l = np.minimum(o, c) - spread
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 0}, index=idx)


def test_bos_requires_body_close_beyond_level():
    closes = [1.0] * 10 + [1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08]
    closes += [1.07] * 5 + [1.09, 1.10, 1.11, 1.12]
    closes += [1.11] * 20
    df = _df_from_closes(closes)
    swings = find_swings(df, 2)
    atr_s = atr(df)
    events = detect_structure(df, swings, 2, atr_s, min_break_abs=0.0001)
    assert any(e["kind"] == "BOS" for e in events["events"])


def test_mss_after_sweep():
    events = [
        {"pos": 10, "kind": "CHoCH", "direction": "bullish", "level": 1.05, "displacement": True},
    ]
    sweeps = [{"pos": 8, "bias": "bullish", "side": "sellside", "level": 1.04}]
    mss = detect_mss(events, sweeps)
    assert len(mss) == 1
    assert mss[0]["kind"] == "MSS"
