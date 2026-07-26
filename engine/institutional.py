"""Institutional narrative and execution-quality rules shared by the engine."""
from __future__ import annotations


TRADE_DIRECTIONS = {"bullish", "bearish"}
SHIFT_KINDS = {"CHoCH", "MSS"}


def latest_directional_event(analysis: dict, direction: str | None = None) -> dict | None:
    events = analysis.get("structure", {}).get("events", [])
    for event in reversed(events):
        if direction is None or event.get("direction") == direction:
            return event
    return None


def event_is_recent(analysis: dict, event: dict | None, max_bars: int = 12) -> bool:
    return bool(event and analysis.get("bars", 0) - 1 - event.get("pos", -10_000) <= max_bars)


def directional_sweep(analysis: dict, direction: str, max_bars: int = 12) -> dict | None:
    matches = [
        sweep for sweep in analysis.get("sweeps", [])
        if sweep.get("bias") == direction and sweep.get("bars_ago", max_bars + 1) <= max_bars
    ]
    return matches[-1] if matches else None


def active_entry_zone(analysis: dict, direction: str) -> dict | None:
    price = analysis.get("price")
    buffer = 0.25 * analysis.get("atr", 0)
    zones = []
    for block in analysis.get("valid_order_blocks", []):
        if block.get("direction") == direction and block["low"] - buffer <= price <= block["high"] + buffer:
            zones.append({"kind": "order_block", **block})
    for gap in analysis.get("fvgs", []):
        if gap.get("direction") == direction and gap.get("status") != "filled" and gap["low"] <= price <= gap["high"]:
            zones.append({"kind": "fvg", **gap})
    breaker_key = "breakers"
    for breaker in analysis.get(breaker_key, []):
        if breaker.get("direction") == direction and breaker["low"] - buffer <= price <= breaker["high"] + buffer:
            zones.append({"kind": "breaker", **breaker})
    return zones[-1] if zones else None


def execution_confirmation(analysis: dict, direction: str, max_bars: int = 8) -> dict:
    """Require a recent, aligned displaced shift after an aligned sweep."""
    event = latest_directional_event(analysis, direction)
    sweep = directional_sweep(analysis, direction, max_bars=max_bars * 2)
    reasons = []
    if not event:
        reasons.append("No aligned structure event")
    elif event.get("kind") not in SHIFT_KINDS:
        reasons.append("Continuation BOS is not an execution confirmation")
    elif not event.get("displacement"):
        reasons.append("Structure shift lacks displacement")
    elif not event_is_recent(analysis, event, max_bars=max_bars):
        reasons.append("Structure shift is stale")
    if not sweep:
        reasons.append("No recent aligned liquidity sweep before confirmation")
    elif event and sweep.get("pos", 10**9) > event.get("pos", -1):
        reasons.append("Liquidity sweep occurred after the structure shift")
    confirmed = not reasons
    return {"confirmed": confirmed, "event": event, "sweep": sweep, "reasons": reasons}


def classify_market_maker_model(analysis: dict) -> dict:
    """Classify the current liquidity-delivery phase without creating a signal."""
    bull_sweep = directional_sweep(analysis, "bullish", max_bars=24)
    bear_sweep = directional_sweep(analysis, "bearish", max_bars=24)
    latest = latest_directional_event(analysis)
    if not latest:
        return {"phase": "ACCUMULATION", "direction": "neutral", "complete": False}
    direction = latest.get("direction")
    sweep = bull_sweep if direction == "bullish" else bear_sweep
    if sweep and sweep["pos"] <= latest["pos"] and latest.get("kind") in SHIFT_KINDS:
        phase = "DISTRIBUTION" if latest.get("displacement") else "MANIPULATION"
        return {"phase": phase, "direction": direction, "complete": bool(latest.get("displacement"))}
    return {"phase": "ACCUMULATION", "direction": direction, "complete": False}
