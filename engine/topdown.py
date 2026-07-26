# engine/topdown.py
"""Top-down SMC/ICT analysis orchestrator — style-driven multi-timeframe ladder."""
from __future__ import annotations

import pandas as pd

from engine import confluence
from engine.data import DataUnavailableError, get_data
from engine.mtf import (
    MAX_DRAW_DISTANCE_PCT,
    NEARBY_POOL_MERGE_PCT,
    _frame_minutes,
    _h1_liquidity_map,
    _load,
    _pick_draw,
    _resample_4h,
)
from engine.trading_style import (
    TF_LABELS,
    all_timeframes,
    ladder_for,
    normalize_trading_style,
    primary_entry_tf,
    timeframe_labels,
)
from utils.logger import get_logger

log = get_logger("engine.topdown")

BIAS_LABELS = {
    "bullish": "BULLISH",
    "bearish": "BEARISH",
    "neutral": "NEUTRAL",
    "mixed": "MIXED",
}


def _resample_daily(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("1D").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open", "High", "Low", "Close"])


def _parent_bias(analysis: dict, tf: str) -> dict:
    """Higher timeframe bias from structure + premium/discount."""
    events = analysis["structure"]["events"]
    pd_info = analysis["premium_discount"]
    trend_map = {1: "BULLISH", -1: "BEARISH", 0: "RANGING"}
    trend = trend_map.get(analysis["structure"]["trend"], "MIXED")

    if not events:
        return {
            "direction": "neutral",
            "bias_label": "NEUTRAL",
            "strength": 0,
            "confidence": 0.5,
            "interval": tf,
            "trend": trend,
            "reason": f"No structure events on {TF_LABELS.get(tf, tf)}",
            "premium_discount": pd_info,
        }

    ev = events[-1]
    direction = ev["direction"]
    strength = 80 if ev.get("displacement") else 60
    aligned = (direction == "bullish" and pd_info["zone"] == "discount") or (
        direction == "bearish" and pd_info["zone"] == "premium"
    )
    if aligned:
        strength = min(100, strength + 15)
    elif pd_info["zone"] == "equilibrium":
        strength = max(0, strength - 10)

    bias_label = BIAS_LABELS.get(direction, "MIXED")
    if pd_info["zone"] == "equilibrium" and direction in ("bullish", "bearish"):
        bias_label = "MIXED"

    return {
        "direction": direction,
        "bias_label": bias_label,
        "strength": strength,
        "confidence": 0.75 if ev.get("displacement") else 0.6,
        "interval": tf,
        "trend": trend,
        "reason": (
            f"{TF_LABELS.get(tf, tf)} bias: {ev['kind']} {direction}"
            f"{' with displacement' if ev.get('displacement') else ''}, "
            f"price in {pd_info['zone']} ({pd_info['position']:.0%} of range)"
        ),
        "premium_discount": pd_info,
        "pdh_pdl": analysis.get("pdh_pdl"),
        "pwh_pwl": analysis.get("pwh_pwl"),
    }


def _resolve_htf_conflict(parent_biases: list[dict]) -> dict | None:
    """Return conflict info when parent timeframes disagree strongly."""
    dirs = [b["direction"] for b in parent_biases if b.get("direction") in ("bullish", "bearish")]
    if len(dirs) < 2:
        return None
    if dirs[0] != dirs[1]:
        return {
            "conflict": True,
            "reason": f"Parent timeframe conflict: {dirs[0]} vs {dirs[1]}",
        }
    return None


def _load_tf(symbol: str, tf: str, fetch: bool, cache: dict) -> pd.DataFrame | None:
    if tf in cache:
        return cache[tf]
    df, _ = _load(symbol, tf, fetch)
    cache[tf] = df
    return df


def topdown_analyze(
    symbol: str,
    fetch: bool,
    trading_style: str = "intraday",
    progress=None,
) -> dict:
    """Run full top-down stack for a trading style.

    Returns analysis dict compatible with confluence.decide(), plus layer
    metadata for the prediction response schema.
    """
    style = normalize_trading_style(trading_style)
    ladder = ladder_for(style)
    notes: list[str] = []

    from services.threshold_service import resolve_thresholds
    thresholds, threshold_version_id = resolve_thresholds(symbol, primary_entry_tf(style), style)

    def note(stage, msg):
        log.info("[%s] %s: %s", symbol, stage, msg)
        if progress:
            progress(stage, msg)

    frames: dict[str, pd.DataFrame | None] = {}
    source = "cache"

    for tf in all_timeframes(style):
        df, src = _load(symbol, tf, fetch)
        if df is not None and src:
            source = src
        frames[tf] = df

    # Resample fallbacks
    if frames.get("240min") is None and frames.get("60min") is not None:
        if len(frames["60min"]) >= 120:
            frames["240min"] = _resample_4h(frames["60min"])
            notes.append("4H resampled from 1H")
    if frames.get("daily") is None and frames.get("240min") is not None:
        if len(frames["240min"]) >= 30:
            frames["daily"] = _resample_daily(frames["240min"])
            notes.append("Daily resampled from 4H")

    # Entry frame selection
    entry_tf = primary_entry_tf(style)
    df_entry = frames.get(entry_tf)
    if df_entry is None:
        for fallback in ladder["setup"] + ladder.get("execution", []) + ["60min", "30min"]:
            if frames.get(fallback) is not None:
                entry_tf = fallback
                df_entry = frames[fallback]
                notes.append(f"Setup frame {primary_entry_tf(style)} unavailable — using {entry_tf}")
                break
    if df_entry is None:
        raise DataUnavailableError(f"No entry-frame data for {symbol} ({style})")

    note("data", f"Entry frame {entry_tf}: {len(df_entry)} candles")

    # Layer A — parent bias
    parent_biases: list[dict] = []
    layer_results: dict[str, dict] = {}
    for tf in ladder["parent"]:
        df_parent = frames.get(tf)
        if df_parent is None or len(df_parent) < 20:
            notes.append(f"Parent frame {tf} unavailable")
            continue
        note("analyze", f"Parent bias on {TF_LABELS.get(tf, tf)}...")
        parent_analysis = confluence.analyze(df_parent, symbol, interval=tf, thresholds=thresholds, trading_style=style)
        bias = _parent_bias(parent_analysis, tf)
        parent_biases.append(bias)
        layer_results[tf] = {"layer": "parent", "analysis": parent_analysis, "bias": bias}

    htf_conflict = _resolve_htf_conflict(parent_biases)
    primary_htf = parent_biases[-1] if parent_biases else None

    # Layer B — structure (1H default)
    structure_biases: list[dict] = []
    for tf in ladder.get("structure", ["60min"]):
        df_struct = frames.get(tf)
        if df_struct is None:
            continue
        note("analyze", f"Structure on {TF_LABELS.get(tf, tf)}...")
        struct_analysis = confluence.analyze(df_struct, symbol, interval=tf, thresholds=thresholds, trading_style=style)
        layer_results[f"struct_{tf}"] = {"layer": "structure", "analysis": struct_analysis}
        events = struct_analysis["structure"]["events"]
        if events:
            ev = events[-1]
            structure_biases.append({"direction": ev["direction"], "kind": ev["kind"], "tf": tf})

    # Layer C — setup on entry frame
    note("analyze", f"Setup analysis on {entry_tf}...")
    analysis = confluence.analyze(df_entry, symbol, interval=entry_tf, thresholds=thresholds, trading_style=style)
    layer_results[entry_tf] = {"layer": "setup", "analysis": analysis}

    # Layer D — execution confirmation (lower TF)
    execution_confirmed = False
    execution_tf = None
    execution_details = None
    target_direction = (primary_htf or {}).get("direction")
    for tf in ladder.get("execution", []):
        df_exec = frames.get(tf)
        if df_exec is None or len(df_exec) < 30:
            continue
        exec_analysis = confluence.analyze(df_exec, symbol, interval=tf, thresholds=thresholds, trading_style=style)
        layer_results[f"exec_{tf}"] = {"layer": "execution", "analysis": exec_analysis}
        if target_direction in ("bullish", "bearish"):
            from engine.institutional import execution_confirmation
            execution_details = execution_confirmation(exec_analysis, target_direction, max_bars=8)
            if execution_details["confirmed"]:
                execution_confirmed = True
                execution_tf = tf
                break

    price = analysis["price"]

    # Inject HTF context into entry analysis
    if primary_htf:
        analysis["htf_bias"] = primary_htf
        analysis["higher_timeframe_bias"] = primary_htf.get("bias_label", "NEUTRAL")
        note("analyze", primary_htf["reason"])

    if htf_conflict:
        analysis["htf_conflict"] = htf_conflict

    analysis["parent_biases"] = parent_biases
    analysis["structure_biases"] = structure_biases
    analysis["execution_confirmed"] = execution_confirmed
    analysis["execution_tf"] = execution_tf
    analysis["execution_details"] = execution_details
    analysis["trading_style"] = style
    analysis["threshold_version_id"] = threshold_version_id
    analysis["layer_results"] = layer_results

    # 1H liquidity map (structure TF or 60min)
    liq_tf = ladder.get("structure", ["60min"])[0]
    df_liq = frames.get(liq_tf)
    if df_liq is None:
        df_liq = frames.get("60min")
    liquidity = None
    draw = None
    if df_liq is not None:
        note("analyze", f"Liquidity map on {TF_LABELS.get(liq_tf, liq_tf)}...")
        h1_analysis = confluence.analyze(df_liq, symbol, interval=liq_tf, thresholds=thresholds, trading_style=style)
        liquidity = _h1_liquidity_map(h1_analysis, price, symbol)
        merge_tol = price * NEARBY_POOL_MERGE_PCT / 100.0
        existing = [p["level"] for p in analysis["pools"]]
        for p in liquidity["above"] + liquidity["below"]:
            if all(abs(p["level"] - lvl) > merge_tol for lvl in existing):
                analysis["pools"].append({
                    "side": p["side"], "level": p["level"], "points": p["points"],
                    "swept": False, "tf": liq_tf,
                })
        bias_dir = (primary_htf or {}).get("direction", "neutral")
        if bias_dir in ("bullish", "bearish"):
            draw = _pick_draw(liquidity, bias_dir, price)
            if draw:
                analysis["liquidity_draw"] = draw
                note("analyze", draw["reason"])

    context = {
        "trading_style": style,
        "timeframes_used": timeframe_labels(style),
        "timeframes": {
            "parent": ladder["parent"],
            "structure": ladder.get("structure", []),
            "setup": ladder["setup"],
            "execution": ladder.get("execution", []),
            "entry": entry_tf,
        },
        "parent_biases": parent_biases,
        "higher_timeframe_bias": primary_htf.get("bias_label") if primary_htf else "NEUTRAL",
        "htf_conflict": htf_conflict,
        "h1_liquidity": liquidity,
        "liquidity_draw": draw,
        "execution_confirmed": execution_confirmed,
        "execution_tf": execution_tf,
        "execution_details": execution_details,
        "layer_results": {k: v.get("layer") for k, v in layer_results.items()},
        "notes": notes,
    }

    return {
        "analysis": analysis,
        "context": context,
        "entry_df": df_entry,
        "entry_tf": entry_tf,
        "source": source,
        "frames": {k: v for k, v in frames.items() if v is not None},
        "threshold_version_id": threshold_version_id,
        "thresholds": thresholds,
    }
