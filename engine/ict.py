# engine/ict.py
"""Inner Circle Trader concepts — valid-signal detection only.

Implemented signals (each with its validity condition):

- Kill zones: London / NY-AM / London-close session windows. Timestamps
  from the data provider are US/Eastern, so the windows are expressed in
  that clock and configurable via env.
- Liquidity sweep (stop hunt): a wick trades through a liquidity pool or
  a recent significant swing and the candle CLOSES BACK on the original
  side. A close through the level is a breakout, not a sweep, and is
  never counted.
- Displacement: candle body larger than a multiple of ATR with a
  dominant body — evidence of institutional initiative.
- Premium / discount: position of price inside the current dealing
  range (from the last structure impulse). Longs are only valid in
  discount, shorts only in premium.
- OTE (optimal trade entry): the 61.8%–79% retracement of the last
  impulse leg.
- Breaker blocks: an order block that failed (was traded through) after
  a liquidity sweep flips polarity and becomes a breaker.
"""
import os
from datetime import time as dtime

import numpy as np
import pandas as pd

# Kill zones in the data feed's clock (Alpha Vantage intraday = US/Eastern).
# Override with env KILLZONES="London=02:00-05:00,NewYork=07:00-10:00".
_DEFAULT_KILLZONES = {
    "London": (dtime(2, 0), dtime(5, 0)),
    "NewYork": (dtime(7, 0), dtime(10, 0)),
    "LondonClose": (dtime(10, 0), dtime(12, 0)),
}


def _load_killzones() -> dict:
    raw = os.getenv("KILLZONES", "").strip()
    if not raw:
        return dict(_DEFAULT_KILLZONES)
    zones = {}
    try:
        for part in raw.split(","):
            name, span = part.split("=")
            start, end = span.split("-")
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            zones[name.strip()] = (dtime(sh, sm), dtime(eh, em))
    except ValueError:
        return dict(_DEFAULT_KILLZONES)
    return zones or dict(_DEFAULT_KILLZONES)


KILLZONES = _load_killzones()


def active_killzone(ts: pd.Timestamp) -> str | None:
    """Name of the kill zone containing ts, or None."""
    t = ts.time()
    for name, (start, end) in KILLZONES.items():
        if start <= t < end:
            return name
    return None


def killzone_flags(df: pd.DataFrame) -> pd.Series:
    """Boolean per-candle 'inside any kill zone' series."""
    times = df.index.time
    mask = np.zeros(len(df), dtype=bool)
    for start, end in KILLZONES.values():
        mask |= (times >= start) & (times < end)
    return pd.Series(mask, index=df.index)


# --------------------------------------------------------------------
# Displacement
# --------------------------------------------------------------------
def displacement_flags(
    df: pd.DataFrame,
    atr_series: pd.Series,
    mult: float = 1.5,
    body_dominance: float = 0.55,
) -> pd.Series:
    """True where the candle is a displacement candle."""
    body = (df["Close"] - df["Open"]).abs()
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return ((body > mult * atr_series) & (body / rng > body_dominance)).fillna(False)


# --------------------------------------------------------------------
# Liquidity sweeps (valid = wick through, close back)
# --------------------------------------------------------------------
def detect_sweeps(
    df: pd.DataFrame,
    pools: list[dict],
    swings: pd.DataFrame,
    recent_bars: int = 24,
    tolerance: float = 0.0,
) -> list[dict]:
    """Valid liquidity grabs within the last `recent_bars` candles.

    Sweep of buy-side liquidity (above equal highs) that closes back
    below is a BEARISH signal; sweep of sell-side is BULLISH. The sweep
    is discarded if any later candle closed beyond the swept level
    (the market accepted the breakout, so it was no grab).
    """
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)
    cutoff = max(0, n - recent_bars)
    sweeps: list[dict] = []

    # Levels worth hunting: equal high/low pools plus the most recent
    # significant swings (session/period highs and lows hold stops too).
    levels: list[dict] = [
        {"level": p["level"], "side": p["side"], "source": "pool", "min_pos": p["last_pos"]}
        for p in pools
    ]
    if not swings.empty:
        for s in swings.sort_values("pos").tail(10).to_dict("records"):
            levels.append({
                "level": s["price"],
                "side": "buyside" if s["kind"] == "high" else "sellside",
                "source": "swing",
                "min_pos": s["pos"],
            })

    for lv in levels:
        level = lv["level"]
        for i in range(max(cutoff, lv["min_pos"] + 1), n):
            if lv["side"] == "buyside":
                pierced = highs[i] > level and closes[i] < level
                accepted_later = (closes[i + 1:] > level).any() if i + 1 < n else False
            else:
                pierced = lows[i] < level and closes[i] > level
                accepted_later = (closes[i + 1:] < level).any() if i + 1 < n else False
            if pierced and not accepted_later:
                # One sweep per liquidity area: nearby levels of the same
                # side are the same stop cluster, not extra confluence.
                duplicate = any(
                    s["side"] == lv["side"] and abs(s["level"] - level) <= tolerance
                    for s in sweeps
                )
                if duplicate:
                    break
                sweeps.append({
                    "pos": i,
                    "time": df.index[i],
                    "level": float(level),
                    "side": lv["side"],
                    "source": lv["source"],
                    "bias": "bearish" if lv["side"] == "buyside" else "bullish",
                    "bars_ago": n - 1 - i,
                })
                break

    return sorted(sweeps, key=lambda s: s["pos"])


# --------------------------------------------------------------------
# Dealing range, premium/discount, OTE
# --------------------------------------------------------------------
def dealing_range(df: pd.DataFrame, structure_events: list[dict], fallback_bars: int = 60) -> dict:
    """Current dealing range from the last structure impulse.

    Bullish impulse: origin swing low -> highest high since the break.
    Bearish impulse: mirror. Without events, the last N bars' extremes.
    """
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    n = len(df)

    if structure_events:
        ev = structure_events[-1]
        start = ev["origin_pos"] if ev.get("origin_pos") is not None else max(0, ev["pos"] - fallback_bars)
        if ev["direction"] == "bullish":
            range_low = ev["origin_price"] if ev.get("origin_price") else float(lows[start:].min())
            range_high = float(highs[ev["pos"]:].max())
            direction = "bullish"
        else:
            range_high = ev["origin_price"] if ev.get("origin_price") else float(highs[start:].max())
            range_low = float(lows[ev["pos"]:].min())
            direction = "bearish"
    else:
        start = max(0, n - fallback_bars)
        range_low = float(lows[start:].min())
        range_high = float(highs[start:].max())
        direction = "neutral"

    if range_high <= range_low:  # degenerate range — widen to recent extremes
        start = max(0, n - fallback_bars)
        range_low = float(lows[start:].min())
        range_high = float(highs[start:].max())

    return {"low": range_low, "high": range_high, "direction": direction}


def premium_discount(price: float, rng: dict) -> dict:
    """Where price sits in the dealing range.

    position: 0.0 = range low, 1.0 = range high.
    zone: 'discount' (<0.45) / 'equilibrium' / 'premium' (>0.55).
    """
    span = rng["high"] - rng["low"]
    position = 0.5 if span <= 0 else (price - rng["low"]) / span
    position = float(np.clip(position, 0.0, 1.0))
    if position < 0.45:
        zone = "discount"
    elif position > 0.55:
        zone = "premium"
    else:
        zone = "equilibrium"
    return {"position": position, "zone": zone}


def ote_zone(rng: dict) -> dict | None:
    """61.8%–79% retracement of the current impulse leg.

    For a bullish leg the OTE sits below price (a pullback buy zone);
    for a bearish leg above. Returns None when there is no directional leg.
    """
    if rng["direction"] == "bullish":
        span = rng["high"] - rng["low"]
        return {
            "direction": "bullish",
            "low": rng["high"] - 0.79 * span,
            "high": rng["high"] - 0.618 * span,
        }
    if rng["direction"] == "bearish":
        span = rng["high"] - rng["low"]
        return {
            "direction": "bearish",
            "low": rng["low"] + 0.618 * span,
            "high": rng["low"] + 0.79 * span,
        }
    return None


def price_in_zone(price: float, zone: dict | None) -> bool:
    return bool(zone and zone["low"] <= price <= zone["high"])


def pd_position_series(df: pd.DataFrame, structure_events: list[dict]) -> pd.Series:
    """Per-bar premium/discount position from structure-derived dealing range."""
    closes = df["Close"].to_numpy()
    positions = np.full(len(df), 0.5)
    for i in range(len(df)):
        events = [e for e in structure_events if e["pos"] <= i]
        rng = dealing_range(df.iloc[: i + 1], events)
        positions[i] = premium_discount(float(closes[i]), rng)["position"]
    return pd.Series(positions, index=df.index)


# --------------------------------------------------------------------
# Breaker blocks
# --------------------------------------------------------------------
def detect_breakers(df: pd.DataFrame, order_blocks: list[dict], sweeps: list[dict]) -> list[dict]:
    """Order blocks that failed after a liquidity sweep flip polarity.

    A bullish OB traded through after buy-side was swept becomes a
    bearish breaker (resistance), and vice versa. The breaker stays
    valid until price closes back through it again.
    """
    closes = df["Close"].to_numpy()
    n = len(df)
    breakers: list[dict] = []

    sweep_positions = [s["pos"] for s in sweeps]

    for ob in order_blocks:
        if ob["status"] != "invalidated" or ob["invalidated_pos"] is None:
            continue
        inv = ob["invalidated_pos"]
        # Validity: the failure must follow a sweep (stop hunt fueled the reversal).
        if not any(p <= inv for p in sweep_positions):
            continue

        new_direction = "bearish" if ob["direction"] == "bullish" else "bullish"

        # Still valid only if price hasn't closed back through the zone since.
        future = slice(inv + 1, n)
        if new_direction == "bearish":
            reclaimed = (closes[future] > ob["high"]).any()
        else:
            reclaimed = (closes[future] < ob["low"]).any()
        if reclaimed:
            continue

        breakers.append({
            "direction": new_direction,
            "low": ob["low"],
            "high": ob["high"],
            "pos": ob["pos"],
            "flipped_at": inv,
            "time": df.index[min(inv, n - 1)],
        })

    return breakers
