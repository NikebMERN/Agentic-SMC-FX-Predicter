# engine/smc.py
"""Smart Money Concepts — valid-signal detection only.

Every detector here enforces the validity rules traders actually use,
instead of counting every raw pattern:

- Structure breaks (BOS / CHoCH) require a candle BODY CLOSE beyond the
  swing level, not a wick poke.
- Order blocks only exist when the impulse away from them broke
  structure; they are tracked through their life cycle
  (fresh -> mitigated -> invalidated) and invalidated blocks are never
  used as entry zones (they become breaker candidates instead).
- Fair value gaps use the correct three-candle definition, must be
  created by a displacement candle, and are dropped once fully filled.
- Liquidity pools are clusters of equal highs/lows and carry their
  swept/unswept state.
"""
import numpy as np
import pandas as pd


# --------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def find_swings(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Confirmed fractal swing highs/lows.

    A swing is only confirmed `window` candles after it forms — that
    confirmation delay is respected by detect_structure so no signal
    looks into the future.
    """
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    rows = []
    for i in range(window, len(df) - window):
        left = slice(i - window, i)
        right = slice(i + 1, i + window + 1)
        if highs[i] > highs[left].max() and highs[i] > highs[right].max():
            rows.append({"pos": i, "time": df.index[i], "kind": "high", "price": float(highs[i])})
        if lows[i] < lows[left].min() and lows[i] < lows[right].min():
            rows.append({"pos": i, "time": df.index[i], "kind": "low", "price": float(lows[i])})
    return pd.DataFrame(rows, columns=["pos", "time", "kind", "price"])


# --------------------------------------------------------------------
# Market structure: BOS / CHoCH (close-confirmed)
# --------------------------------------------------------------------
def detect_structure(
    df: pd.DataFrame,
    swings: pd.DataFrame,
    window: int = 3,
    atr_series: pd.Series | None = None,
    displacement_mult: float = 1.2,
) -> dict:
    """Walk the candles chronologically tracking structure state.

    Returns {'events': [...], 'trend': +1|-1|0}.

    Each event: pos, time, kind ('BOS'|'CHoCH'), direction
    ('bullish'|'bearish'), level (broken swing price), displacement
    (bool — breaking candle body > displacement_mult * ATR),
    origin_pos/origin_price (swing that started the impulse leg, used
    for OTE and dealing-range maths).
    """
    closes = df["Close"].to_numpy()
    opens = df["Open"].to_numpy()
    atr_np = atr_series.to_numpy() if atr_series is not None else None

    events: list[dict] = []
    trend = 0
    ref_high: dict | None = None
    ref_low: dict | None = None
    swing_records = swings.sort_values("pos").to_dict("records")
    si = 0
    confirmed_highs: list[dict] = []
    confirmed_lows: list[dict] = []

    for i in range(len(df)):
        # Swings become usable only once confirmed (window bars later).
        while si < len(swing_records) and swing_records[si]["pos"] + window <= i:
            s = swing_records[si]
            if s["kind"] == "high":
                ref_high = s
                confirmed_highs.append(s)
            else:
                ref_low = s
                confirmed_lows.append(s)
            si += 1

        close = closes[i]
        body = abs(close - opens[i])
        displaced = bool(
            atr_np is not None and not np.isnan(atr_np[i]) and atr_np[i] > 0
            and body > displacement_mult * atr_np[i]
        )

        if ref_high is not None and close > ref_high["price"]:
            origin = confirmed_lows[-1] if confirmed_lows else None
            events.append({
                "pos": i,
                "time": df.index[i],
                "kind": "BOS" if trend >= 0 else "CHoCH",
                "direction": "bullish",
                "level": ref_high["price"],
                "displacement": displaced,
                "origin_pos": origin["pos"] if origin else None,
                "origin_price": origin["price"] if origin else None,
            })
            trend = 1
            ref_high = None  # wait for the next confirmed swing high
        elif ref_low is not None and close < ref_low["price"]:
            origin = confirmed_highs[-1] if confirmed_highs else None
            events.append({
                "pos": i,
                "time": df.index[i],
                "kind": "BOS" if trend <= 0 else "CHoCH",
                "direction": "bearish",
                "level": ref_low["price"],
                "displacement": displaced,
                "origin_pos": origin["pos"] if origin else None,
                "origin_price": origin["price"] if origin else None,
            })
            trend = -1
            ref_low = None

    return {"events": events, "trend": trend}


# --------------------------------------------------------------------
# Order blocks (validated by structure break, life-cycle tracked)
# --------------------------------------------------------------------
def detect_order_blocks(
    df: pd.DataFrame,
    structure_events: list[dict],
    lookback: int = 15,
) -> list[dict]:
    """Order blocks derived only from structure-breaking impulses.

    Bullish OB: last bearish candle before the impulse that closed above
    a swing high. Bearish OB is the mirror. Status:
      fresh       — price never returned to the zone
      mitigated   — price tapped the zone but the block held
      invalidated — price closed through the block (unusable for entry;
                    kept because it may act as a breaker block)
    """
    opens = df["Open"].to_numpy()
    closes = df["Close"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    n = len(df)
    blocks: list[dict] = []

    for ev in structure_events:
        i = ev["pos"]
        scan_start = max(0, i - lookback)
        if ev.get("origin_pos") is not None:
            scan_start = max(scan_start, ev["origin_pos"])

        origin_idx = None
        if ev["direction"] == "bullish":
            for j in range(i - 1, scan_start - 1, -1):
                if closes[j] < opens[j]:
                    origin_idx = j
                    break
        else:
            for j in range(i - 1, scan_start - 1, -1):
                if closes[j] > opens[j]:
                    origin_idx = j
                    break
        if origin_idx is None:
            continue

        zone_low = float(lows[origin_idx])
        zone_high = float(highs[origin_idx])

        status, mitigated_pos, invalidated_pos = "fresh", None, None
        future = slice(i + 1, n)
        if ev["direction"] == "bullish":
            touched = lows[future] <= zone_high
            broken = closes[future] < zone_low
        else:
            touched = highs[future] >= zone_low
            broken = closes[future] > zone_high
        if touched.any():
            status = "mitigated"
            mitigated_pos = i + 1 + int(np.argmax(touched))
        if broken.any():
            status = "invalidated"
            invalidated_pos = i + 1 + int(np.argmax(broken))

        blocks.append({
            "direction": ev["direction"],
            "pos": origin_idx,
            "time": df.index[origin_idx],
            "low": zone_low,
            "high": zone_high,
            "event_pos": i,
            "event_kind": ev["kind"],
            "displacement": ev["displacement"],
            "status": status,
            "mitigated_pos": mitigated_pos,
            "invalidated_pos": invalidated_pos,
        })

    return blocks


def valid_order_blocks(blocks: list[dict]) -> list[dict]:
    """Blocks still usable as entry zones (fresh or once-mitigated)."""
    return [b for b in blocks if b["status"] != "invalidated"]


# --------------------------------------------------------------------
# Fair value gaps (correct 3-candle logic, displacement required)
# --------------------------------------------------------------------
def detect_fvg(
    df: pd.DataFrame,
    atr_series: pd.Series,
    require_displacement: bool = True,
    displacement_mult: float = 1.0,
) -> list[dict]:
    """Three-candle imbalances.

    Bullish FVG: high[i-1] < low[i+1] (gap left under price as it drove
    up). Bearish FVG: low[i-1] > high[i+1]. The middle candle must be a
    displacement candle for the gap to be a valid signal. Fully filled
    gaps are discarded; partially traded gaps stay valid.
    """
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    opens = df["Open"].to_numpy()
    closes = df["Close"].to_numpy()
    atr_np = atr_series.to_numpy()
    n = len(df)
    gaps: list[dict] = []

    bull_idx = np.where(highs[:-2] < lows[2:])[0] + 1  # middle-candle index
    bear_idx = np.where(lows[:-2] > highs[2:])[0] + 1

    def build(i: int, direction: str) -> dict | None:
        body = abs(closes[i] - opens[i])
        displaced = bool(not np.isnan(atr_np[i]) and atr_np[i] > 0 and body >= displacement_mult * atr_np[i])
        if require_displacement and not displaced:
            return None

        if direction == "bullish":
            zone_low, zone_high = float(highs[i - 1]), float(lows[i + 1])
        else:
            zone_low, zone_high = float(highs[i + 1]), float(lows[i - 1])

        status = "open"
        future = slice(i + 2, n)
        if direction == "bullish":
            filled = lows[future] <= zone_low
            partial = lows[future] <= zone_high
        else:
            filled = highs[future] >= zone_high
            partial = highs[future] >= zone_low
        if filled.any():
            return None  # fully filled — no longer a valid gap
        if partial.any():
            status = "partial"

        return {
            "direction": direction,
            "pos": i,
            "time": df.index[i],
            "low": zone_low,
            "high": zone_high,
            "displacement": displaced,
            "status": status,
        }

    for i in bull_idx:
        g = build(int(i), "bullish")
        if g:
            gaps.append(g)
    for i in bear_idx:
        g = build(int(i), "bearish")
        if g:
            gaps.append(g)

    return sorted(gaps, key=lambda g: g["pos"])


# --------------------------------------------------------------------
# Liquidity pools (equal highs / equal lows, swept-state tracked)
# --------------------------------------------------------------------
def detect_liquidity_pools(
    df: pd.DataFrame,
    swings: pd.DataFrame,
    tolerance: float,
    min_points: int = 2,
) -> list[dict]:
    """Clusters of equal swing highs (buy-side) / lows (sell-side).

    tolerance is an absolute price distance (caller usually passes a
    fraction of ATR). Each pool records whether it has been swept and
    whether the sweeping candle closed back inside (a rejection — the
    raw material for ICT sweep signals) or closed through (a breakout).
    """
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)
    pools: list[dict] = []

    def cluster(points: pd.DataFrame, side: str):
        pts = points.sort_values("price").to_dict("records")
        group: list[dict] = []
        for p in pts:
            if group and abs(p["price"] - group[-1]["price"]) > tolerance:
                emit(group, side)
                group = []
            group.append(p)
        emit(group, side)

    def emit(group: list[dict], side: str):
        if len(group) < min_points:
            return
        level = max(g["price"] for g in group) if side == "buyside" else min(g["price"] for g in group)
        last_pos = max(g["pos"] for g in group)

        swept, swept_pos, sweep_rejected = False, None, False
        future = slice(last_pos + 1, n)
        if side == "buyside":
            breach = highs[future] > level
        else:
            breach = lows[future] < level
        if breach.any():
            swept = True
            swept_pos = last_pos + 1 + int(np.argmax(breach))
            if side == "buyside":
                sweep_rejected = closes[swept_pos] < level
            else:
                sweep_rejected = closes[swept_pos] > level

        pools.append({
            "side": side,
            "level": float(level),
            "points": len(group),
            "positions": [g["pos"] for g in group],
            "last_pos": last_pos,
            "swept": swept,
            "swept_pos": swept_pos,
            "sweep_rejected": sweep_rejected,
        })

    if not swings.empty:
        cluster(swings[swings["kind"] == "high"], "buyside")
        cluster(swings[swings["kind"] == "low"], "sellside")

    return pools
