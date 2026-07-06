# engine/prediction_response.py
"""Standard prediction JSON schema (section H)."""
from __future__ import annotations

from datetime import datetime, timezone

from engine.confluence import ACTION_BUY, ACTION_SELL, ACTION_WAIT
from engine.data import to_display_pair, to_oanda_instrument
from engine.trading_style import TF_LABELS, normalize_trading_style, timeframe_labels
from utils.compliance import DISCLAIMER

MODEL_VERSION = "smc-ict-v1"


def _serialize_events(analysis: dict, kind_filter: tuple[str, ...] | None = None) -> list[dict]:
    out = []
    for ev in analysis.get("structure", {}).get("events", [])[-5:]:
        if kind_filter and ev.get("kind") not in kind_filter:
            continue
        out.append({
            "kind": ev["kind"],
            "direction": ev["direction"].upper(),
            "level": ev.get("level"),
            "displacement": ev.get("displacement", False),
            "time": str(ev.get("time", "")),
        })
    return out


def build_prediction_response(
    symbol: str,
    trading_style: str,
    decision: dict,
    analysis: dict,
    *,
    mtf_context: dict | None = None,
    validation: dict | None = None,
) -> dict:
    """Build section H JSON from pipeline outputs."""
    style = normalize_trading_style(trading_style)
    action = decision.get("action", "NO_TRADE")
    direction_map = {
        ACTION_BUY: "BUY_BIAS",
        ACTION_SELL: "SELL_BIAS",
        ACTION_WAIT: "WAIT_FOR_CONFIRMATION",
        "NO_TRADE": "NO_TRADE",
    }
    direction = direction_map.get(action, action)

    tfs = timeframe_labels(style)
    if mtf_context and mtf_context.get("timeframes_used"):
        tfs = mtf_context["timeframes_used"]

    htf_bias = (
        analysis.get("higher_timeframe_bias")
        or (analysis.get("htf_bias") or {}).get("bias_label")
        or "NEUTRAL"
    )

    sweeps = [
        {
            "side": s.get("side"),
            "level": s.get("level"),
            "bias": s.get("bias", "").upper(),
            "barsAgo": s.get("bars_ago"),
        }
        for s in analysis.get("sweeps", [])[-5:]
    ]

    buy_side = [p["level"] for p in analysis.get("pools", []) if p.get("side") == "buyside" and not p.get("swept")]
    sell_side = [p["level"] for p in analysis.get("pools", []) if p.get("side") == "sellside" and not p.get("swept")]

    fvgs = [
        {
            "direction": g["direction"].upper(),
            "low": g["low"],
            "high": g["high"],
            "status": g["status"],
        }
        for g in analysis.get("fvgs", [])[-5:]
    ]
    obs = [
        {
            "direction": ob["direction"].upper(),
            "low": ob["low"],
            "high": ob["high"],
            "status": ob["status"],
        }
        for ob in analysis.get("valid_order_blocks", [])[-5:]
    ]

    pd_info = analysis.get("premium_discount", {})
    entry = decision.get("entry")
    stop = decision.get("invalidation_price") or decision.get("stop_loss")
    target = decision.get("target_liquidity") or decision.get("take_profit")

    reasoning_text = ". ".join(decision.get("reasoning", [])[:8])
    if not reasoning_text:
        reasoning_text = "No confluence signals met the minimum threshold for a directional bias."

    invalid_reasons = list(decision.get("invalid_reasons") or decision.get("no_trade_reasons") or [])
    if validation and validation.get("warnings"):
        invalid_reasons.extend(validation["warnings"])

    return {
        "pair": to_display_pair(symbol),
        "oandaInstrument": to_oanda_instrument(symbol),
        "tradingStyle": style,
        "direction": direction,
        "confidence": decision.get("confidence", 0.0),
        "score": decision.get("score", decision.get("weighted_score", 0)),
        "timeframesUsed": tfs,
        "higherTimeframeBias": htf_bias,
        "marketStructure": {
            "trend": decision.get("market_trend") or "MIXED",
            "bos": _serialize_events(analysis, ("BOS",)),
            "choch": _serialize_events(analysis, ("CHoCH",)),
            "mss": _serialize_events(analysis, ("MSS",)),
        },
        "liquidity": {
            "buySideLiquidity": buy_side[:10],
            "sellSideLiquidity": sell_side[:10],
            "sweeps": sweeps,
        },
        "pdArrays": {
            "fairValueGaps": fvgs,
            "orderBlocks": obs,
            "premiumDiscount": {
                "zone": pd_info.get("zone"),
                "position": pd_info.get("position"),
                "dealingRange": analysis.get("dealing_range"),
                "pdhPdl": analysis.get("pdh_pdl"),
                "pwhPwl": analysis.get("pwh_pwl"),
            },
        },
        "entryPlan": {
            "entryZoneLow": entry,
            "entryZoneHigh": entry,
            "invalidationPrice": stop,
            "targetLiquidityPrice": target,
            "riskReward": decision.get("risk_reward"),
        },
        "reasoning": reasoning_text,
        "invalidReasons": invalid_reasons,
        "riskWarning": DISCLAIMER,
        "modelVersion": MODEL_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
    }
