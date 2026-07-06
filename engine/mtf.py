# engine/mtf.py
"""Liquidity-first multi-timeframe analysis.

The trading model, top down:
  - 4H (240min): TECHNICAL BIAS — market structure, dealing range and
    premium/discount decide which side we are allowed to trade.
  - 1H (60min): EXTERNAL LIQUIDITY — the map of unswept liquidity pools
    (equal highs/lows, old swing extremes). The nearest unswept pool in
    the bias direction is the DRAW ON LIQUIDITY (the magnet price is
    expected to run to); pools behind price are the fuel that was or
    will be grabbed before the move.
  - 30min: ENTRY — the base analysis/decision runs on this frame, so
    entry confirmation (CHoCH/BOS, sweeps, order blocks) and the final
    entry/SL come from 30min structure.

Degrades gracefully: if a frame cannot be fetched, 4H is resampled from
1H, and the entry frame falls back to whatever data exists — the notes
in the output say exactly what was used.
"""
import pandas as pd

from engine import confluence
from engine.data import DataUnavailableError, get_data
from engine.risk_calc import pip_size_for
from utils.logger import get_logger

log = get_logger("engine.mtf")

BIAS_TF = "240min"
LIQUIDITY_TF = "60min"
ENTRY_TF = "30min"

MAX_DRAW_DISTANCE_PCT = 1.5   # a liquidity draw farther than this is ignored
NEARBY_POOL_MERGE_PCT = 0.02  # dedupe pools closer together than this


def _frame_minutes(df: pd.DataFrame) -> float | None:
    """Median candle spacing in minutes (the cache may serve a coarser
    frame than requested — label data by what it actually is)."""
    if df is None or len(df) < 3:
        return None
    deltas = df.index.to_series().diff().dropna()
    if deltas.empty:
        return None
    return float(deltas.median().total_seconds() / 60)


def _load(symbol: str, interval: str, fetch: bool):
    try:
        df, source = get_data(symbol, interval, fetch=fetch)
        return (df, source) if not df.empty else (None, None)
    except (DataUnavailableError, ValueError) as exc:
        log.info("%s %s unavailable: %s", symbol, interval, exc)
        return None, None


def _resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    out = df_1h.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open", "High", "Low", "Close"])
    return out


def _h4_bias(analysis: dict) -> dict:
    """Technical bias from the 4H frame: structure + premium/discount."""
    events = analysis["structure"]["events"]
    pd_info = analysis["premium_discount"]
    if not events:
        return {
            "direction": "neutral", "strength": 0, "confidence": 0.5,
            "interval": BIAS_TF, "reason": "No 4H structure events",
        }
    ev = events[-1]
    direction = ev["direction"]
    strength = 80 if ev.get("displacement") else 60
    # premium/discount agreement strengthens the bias, disagreement weakens it
    aligned = (direction == "bullish" and pd_info["zone"] == "discount") or (
        direction == "bearish" and pd_info["zone"] == "premium"
    )
    if aligned:
        strength = min(100, strength + 15)
    reason = (
        f"4H technical bias: {ev['kind']} {direction}"
        f"{' with displacement' if ev.get('displacement') else ''}, "
        f"price in {pd_info['zone']} ({pd_info['position']:.0%} of 4H range)"
    )
    return {
        "direction": direction,
        "strength": strength,
        "confidence": 0.75 if ev.get("displacement") else 0.6,
        "interval": BIAS_TF,
        "reason": reason,
        "trend": analysis["structure"]["trend"],
        "premium_discount": pd_info,
    }


def _h1_liquidity_map(analysis: dict, price: float, symbol: str) -> dict:
    """External liquidity from the 1H frame: unswept pools around price."""
    pip = pip_size_for(symbol)
    above, below = [], []
    for p in analysis["pools"]:
        if p["swept"]:
            continue
        entry = {
            "level": p["level"],
            "side": p["side"],
            "points": p.get("points", 1),
            "pips_away": round(abs(p["level"] - price) / pip, 1),
            "tf": LIQUIDITY_TF,
        }
        (above if p["level"] > price else below).append(entry)
    above.sort(key=lambda x: x["level"])          # nearest first
    below.sort(key=lambda x: -x["level"])

    recent_sweeps = [
        {
            "side": s["side"], "level": s["level"], "bias": s["bias"],
            "bars_ago": s["bars_ago"], "tf": LIQUIDITY_TF,
        }
        for s in analysis["sweeps"]
    ]
    return {"above": above, "below": below, "recent_sweeps": recent_sweeps}


def _pick_draw(liquidity: dict, bias_direction: str, price: float) -> dict | None:
    """The draw on liquidity: nearest unswept external pool in the bias
    direction, within a realistic distance."""
    pools = liquidity["above"] if bias_direction == "bullish" else liquidity["below"]
    max_dist = price * MAX_DRAW_DISTANCE_PCT / 100.0
    for p in pools:
        if abs(p["level"] - price) <= max_dist:
            return {
                "direction": bias_direction,
                "level": p["level"],
                "pips_away": p["pips_away"],
                "points": p["points"],
                "reason": (
                    f"1H external liquidity: {'buy-side' if bias_direction == 'bullish' else 'sell-side'} "
                    f"pool at {p['level']:.5f} ({p['pips_away']} pips away, "
                    f"{p['points']} equal touch(es)) is the draw on liquidity"
                ),
            }
    return None


def mtf_analyze(symbol: str, fetch: bool, progress=None, trading_style: str = "intraday") -> dict:
    """Run the style-driven top-down stack (delegates to engine.topdown).

    Returns {"analysis": <entry-frame analysis enriched with htf_bias,
    liquidity_draw and merged 1H pools>, "context": <per-frame summary>,
    "entry_df": DataFrame, "entry_tf": str, "source": str}.
    """
    from engine.topdown import topdown_analyze
    return topdown_analyze(symbol, fetch, trading_style=trading_style, progress=progress)


def _mtf_analyze_legacy(symbol: str, fetch: bool, progress=None) -> dict:
    """Legacy fixed 4H -> 1H -> 30min stack (kept for reference/tests)."""
    def note(stage, msg):
        log.info("[%s] %s: %s", symbol, stage, msg)
        if progress:
            progress(stage, msg)

    notes = []

    # ---- entry frame (30min, fallback to 60min then default cache) ----
    entry_tf = ENTRY_TF
    df_entry, source = _load(symbol, ENTRY_TF, fetch)
    actual_minutes = _frame_minutes(df_entry)
    if df_entry is not None and actual_minutes and actual_minutes > 40:
        # cache served a coarser frame than requested — label it honestly
        entry_tf = LIQUIDITY_TF
        notes.append("30min data unavailable — entry frame fell back to 60min cache")
    if df_entry is None:
        entry_tf = LIQUIDITY_TF
        df_entry, source = _load(symbol, LIQUIDITY_TF, fetch)
        notes.append(f"30min data unavailable — entry frame fell back to {entry_tf}")
    if df_entry is None:
        raise DataUnavailableError(f"No entry-frame data for {symbol}")
    note("data", f"Entry frame {entry_tf}: {len(df_entry)} candles ({source})")

    # ---- 1H liquidity frame -------------------------------------------
    df_h1, _ = _load(symbol, LIQUIDITY_TF, fetch)
    if df_h1 is None and entry_tf == LIQUIDITY_TF:
        df_h1 = df_entry
    if df_h1 is None:
        notes.append("1H data unavailable — liquidity map limited to the entry frame")

    # ---- 4H bias frame (resampled from 1H when not fetchable) ---------
    df_h4, _ = _load(symbol, BIAS_TF, fetch)
    if df_h4 is None and df_h1 is not None and len(df_h1) >= 120:
        df_h4 = _resample_4h(df_h1)
        notes.append("4H data resampled from 1H")
    if df_h4 is not None and len(df_h4) < 60:
        df_h4 = None

    # ---- analyses ------------------------------------------------------
    note("analyze", f"30min entry analysis ({len(df_entry)} candles)...")
    analysis = confluence.analyze(df_entry, symbol)
    price = analysis["price"]

    h4_summary = None
    if df_h4 is not None:
        note("analyze", "4H technical analysis (structure, premium/discount)...")
        h4_analysis = confluence.analyze(df_h4, symbol)
        h4_summary = _h4_bias(h4_analysis)
        analysis["htf_bias"] = h4_summary
        note("analyze", h4_summary["reason"])

    liquidity = None
    draw = None
    if df_h1 is not None:
        note("analyze", "1H external liquidity map...")
        h1_analysis = confluence.analyze(df_h1, symbol)
        liquidity = _h1_liquidity_map(h1_analysis, price, symbol)
        # 1H pools become first-class TP candidates on the entry frame
        merge_tol = price * NEARBY_POOL_MERGE_PCT / 100.0
        existing = [p["level"] for p in analysis["pools"]]
        for p in liquidity["above"] + liquidity["below"]:
            if all(abs(p["level"] - lvl) > merge_tol for lvl in existing):
                analysis["pools"].append({
                    "side": p["side"], "level": p["level"], "points": p["points"],
                    "swept": False, "tf": LIQUIDITY_TF,
                })
        bias_dir = (h4_summary or {}).get("direction", "neutral")
        if bias_dir in ("bullish", "bearish"):
            draw = _pick_draw(liquidity, bias_dir, price)
            if draw:
                analysis["liquidity_draw"] = draw
                note("analyze", draw["reason"])
        n_above = len(liquidity["above"])
        n_below = len(liquidity["below"])
        note("analyze", f"1H liquidity: {n_above} unswept pool(s) above, {n_below} below")

    context = {
        "timeframes": {"bias": BIAS_TF, "liquidity": LIQUIDITY_TF, "entry": entry_tf},
        "h4_bias": h4_summary,
        "h1_liquidity": liquidity,
        "liquidity_draw": draw,
        "notes": notes,
    }
    return {
        "analysis": analysis,
        "context": context,
        "entry_df": df_entry,
        "entry_tf": entry_tf,
        "source": source,
    }
