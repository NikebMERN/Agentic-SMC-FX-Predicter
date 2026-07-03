# engine/signals_export.py
"""Export structured SMC/ICT signal records from an analysis dict."""
from __future__ import annotations

from engine import ict


def _strength_from_weight(weight: float, max_weight: float = 2.5) -> int:
    return int(min(100, max(0, round((weight / max_weight) * 100))))


def export_signals(analysis: dict, interval: str = "60min") -> list[dict]:
    """Convert analysis into machine-readable signal records."""
    signals: list[dict] = []
    n = analysis["bars"]
    price = analysis["price"]
    buffer = 0.5 * analysis["atr"]
    last_idx = n - 1

    for ev in analysis["structure"].get("events", [])[-3:]:
        age = last_idx - ev["pos"]
        signals.append({
            "name": ev["kind"],
            "framework": "SMC",
            "direction": ev["direction"],
            "timeframe": interval,
            "strength": _strength_from_weight(2.5 if ev["kind"] == "CHoCH" else 2.0),
            "confidence": 0.85 if ev.get("displacement") else 0.65,
            "price_low": ev["level"],
            "price_high": ev["level"],
            "candle_start": ev["pos"],
            "candle_end": last_idx,
            "validation_reason": f"Body close beyond swing at {ev['level']:.5f}",
            "invalidation_reason": f"Close back through {ev['level']:.5f}",
            "status": "expired" if age > 40 else "active",
        })

    for sweep in analysis.get("sweeps", [])[-3:]:
        signals.append({
            "name": "liquidity_sweep",
            "framework": "ICT",
            "direction": sweep["bias"],
            "timeframe": interval,
            "strength": _strength_from_weight(2.0),
            "confidence": 0.8,
            "price_low": sweep["level"],
            "price_high": sweep["level"],
            "candle_start": max(0, last_idx - sweep.get("bars_ago", 0)),
            "candle_end": last_idx,
            "validation_reason": f"{sweep['side']} liquidity swept and rejected",
            "invalidation_reason": "Price accepts beyond swept level",
            "status": "active" if sweep.get("bars_ago", 99) <= 24 else "expired",
        })

    for ob in analysis.get("valid_order_blocks", []):
        if ob["low"] - buffer <= price <= ob["high"] + buffer:
            signals.append({
                "name": "order_block",
                "framework": "SMC",
                "direction": ob["direction"],
                "timeframe": interval,
                "strength": _strength_from_weight(1.5 if ob["status"] == "fresh" else 0.75),
                "confidence": 0.75 if ob["status"] == "fresh" else 0.55,
                "price_low": ob["low"],
                "price_high": ob["high"],
                "candle_start": ob.get("pos", last_idx),
                "candle_end": last_idx,
                "validation_reason": f"Valid {ob['status']} OB after {ob.get('event_kind', 'structure')}",
                "invalidation_reason": "Full mitigation or close through zone",
                "status": ob["status"],
            })

    for gap in analysis.get("fvgs", []):
        if gap["low"] <= price <= gap["high"]:
            signals.append({
                "name": "fair_value_gap",
                "framework": "SMC",
                "direction": gap["direction"],
                "timeframe": interval,
                "strength": _strength_from_weight(1.0 if gap["status"] == "open" else 0.5),
                "confidence": 0.7 if gap["status"] == "open" else 0.5,
                "price_low": gap["low"],
                "price_high": gap["high"],
                "candle_start": gap.get("pos", last_idx),
                "candle_end": last_idx,
                "validation_reason": "Displacement-created imbalance unfilled",
                "invalidation_reason": "Gap fully filled",
                "status": gap["status"],
            })

    pd_info = analysis.get("premium_discount", {})
    if pd_info.get("zone") in ("discount", "premium"):
        direction = "bullish" if pd_info["zone"] == "discount" else "bearish"
        signals.append({
            "name": "premium_discount",
            "framework": "ICT",
            "direction": direction,
            "timeframe": interval,
            "strength": int(pd_info.get("position", 0.5) * 100),
            "confidence": 0.6,
            "price_low": analysis.get("dealing_range", {}).get("low"),
            "price_high": analysis.get("dealing_range", {}).get("high"),
            "candle_start": last_idx - 20,
            "candle_end": last_idx,
            "validation_reason": f"Price in {pd_info['zone']} ({pd_info.get('position', 0):.0%} of range)",
            "invalidation_reason": "Price moves to opposing zone without structure",
            "status": "active",
        })

    ote = analysis.get("ote") or {}
    if ote and ict.price_in_zone(price, ote):
        signals.append({
            "name": "ote",
            "framework": "ICT",
            "direction": ote.get("direction", "neutral"),
            "timeframe": interval,
            "strength": 70,
            "confidence": 0.65,
            "price_low": ote.get("low"),
            "price_high": ote.get("high"),
            "candle_start": last_idx - 10,
            "candle_end": last_idx,
            "validation_reason": "Price in 61.8-79% OTE retracement",
            "invalidation_reason": "Impulse leg invalidated",
            "status": "active",
        })

    for br in analysis.get("breakers", []):
        if br["low"] - buffer <= price <= br["high"] + buffer:
            signals.append({
                "name": "breaker_block",
                "framework": "ICT",
                "direction": br["direction"],
                "timeframe": interval,
                "strength": 75,
                "confidence": 0.7,
                "price_low": br["low"],
                "price_high": br["high"],
                "candle_start": br.get("pos", last_idx),
                "candle_end": last_idx,
                "validation_reason": "Failed OB flipped after liquidity event",
                "invalidation_reason": "Close through breaker zone",
                "status": "active",
            })

    if analysis.get("killzone"):
        signals.append({
            "name": "kill_zone",
            "framework": "ICT",
            "direction": "neutral",
            "timeframe": interval,
            "strength": 50,
            "confidence": 0.55,
            "price_low": price,
            "price_high": price,
            "candle_start": last_idx,
            "candle_end": last_idx,
            "validation_reason": f"Active session: {analysis['killzone']}",
            "invalidation_reason": "Session ends",
            "status": "active",
        })

    htf = analysis.get("htf_bias")
    if htf:
        signals.append({
            "name": "htf_bias",
            "framework": "ICT",
            "direction": htf.get("direction", "neutral"),
            "timeframe": htf.get("interval", "240min"),
            "strength": htf.get("strength", 50),
            "confidence": htf.get("confidence", 0.6),
            "price_low": None,
            "price_high": None,
            "candle_start": None,
            "candle_end": None,
            "validation_reason": htf.get("reason", "Higher timeframe structure"),
            "invalidation_reason": "HTF structure break",
            "status": "active",
        })

    return signals
