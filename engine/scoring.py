# engine/scoring.py
"""0–100 SMC/ICT confluence scoring engine with hard vetoes."""
from __future__ import annotations

from engine.confluence import (
    ACTION_BUY,
    ACTION_NO_TRADE,
    ACTION_SELL,
    ACTION_WAIT,
    _collect_votes,
    _detect_wait_setup,
    _stop_and_target,
    normalize_strategy_mode,
)
from schemas.threshold_schema import SmcIctThresholds, min_risk_reward_for_style
from services.threshold_service import resolve_thresholds_model
from utils import settings
from utils.compliance import DISCLAIMER
from utils.logger import get_logger
from engine.institutional import active_entry_zone, execution_confirmation, latest_directional_event

log = get_logger("engine.scoring")

COMPONENT_MAX = {
    "htf_bias": 20,
    "structure": 20,
    "liquidity": 15,
    "displacement": 15,
    "zones": 10,
    "premium_discount": 10,
    "session": 5,
    "risk_filter": 5,
}


def _trend_label(analysis: dict) -> str:
    t = analysis.get("structure", {}).get("trend", 0)
    return {1: "BULLISH", -1: "BEARISH", 0: "RANGING"}.get(t, "MIXED")


def _score_htf_bias(analysis: dict, direction: str) -> tuple[int, list[str]]:
    htf = analysis.get("htf_bias") or {}
    label = analysis.get("higher_timeframe_bias") or htf.get("bias_label", "NEUTRAL")
    htf_dir = htf.get("direction", "neutral")
    reasons: list[str] = []

    if htf_dir == direction:
        pts = COMPONENT_MAX["htf_bias"]
        reasons.append(f"HTF bias aligned ({label})")
    elif htf_dir == "neutral" or label == "MIXED":
        pts = COMPONENT_MAX["htf_bias"] // 2
        reasons.append(f"HTF bias mixed/neutral ({label})")
    else:
        pts = 0
        reasons.append(f"HTF bias conflicts ({label} vs {direction})")

    conflict = analysis.get("htf_conflict")
    if conflict:
        pts = max(0, pts - 10)
        reasons.append(conflict.get("reason", "HTF conflict"))
    return pts, reasons


def _score_structure(analysis: dict, direction: str) -> tuple[int, list[str]]:
    events = analysis["structure"]["events"]
    if not events:
        return 0, ["No structure events on setup timeframe"]
    ev = events[-1]
    if ev["direction"] != direction:
        return 0, [f"Latest structure is {ev['direction']}, not {direction}"]
    pts = 12 if ev["kind"] in ("CHoCH", "MSS") else 10
    if ev.get("displacement"):
        pts = min(COMPONENT_MAX["structure"], pts + 5)
    return min(COMPONENT_MAX["structure"], pts), [
        f"{ev['kind']} {ev['direction']} on setup TF"
        + (" with displacement" if ev.get("displacement") else "")
    ]


def _score_liquidity(analysis: dict, direction: str) -> tuple[int, list[str]]:
    sweeps = analysis.get("sweeps", [])
    matching = [s for s in sweeps if s.get("bias") == direction]
    if matching:
        return COMPONENT_MAX["liquidity"], [
            f"Liquidity sweep supports {direction} ({matching[-1]['side']} at {matching[-1]['level']:.5f})"
        ]
    draw = analysis.get("liquidity_draw") or {}
    if draw.get("direction") == direction:
        return COMPONENT_MAX["liquidity"] - 5, ["Draw on liquidity aligned"]
    return 0, ["No recent liquidity sweep in bias direction"]


def _score_displacement(analysis: dict, direction: str) -> tuple[int, list[str]]:
    events = analysis["structure"]["events"]
    if events and events[-1].get("displacement") and events[-1]["direction"] == direction:
        return COMPONENT_MAX["displacement"], ["Displacement confirmed on structure break"]
    for gap in analysis.get("fvgs", []):
        if gap.get("displacement") and gap["direction"] == direction and gap["status"] != "filled":
            return COMPONENT_MAX["displacement"] - 3, ["Displacement FVG present"]
    return 0, ["No displacement evidence"]


def _score_zones(analysis: dict, direction: str) -> tuple[int, list[str]]:
    price = analysis["price"]
    buffer = 0.5 * analysis["atr"]
    pts = 0
    reasons: list[str] = []
    for ob in analysis.get("valid_order_blocks", []):
        if ob["direction"] == direction and ob["low"] - buffer <= price <= ob["high"] + buffer:
            pts = max(pts, 8 if ob["status"] == "fresh" else 5)
            reasons.append(f"Price at {ob['status']} {direction} order block")
    for gap in analysis.get("fvgs", []):
        if gap["direction"] == direction and gap["low"] <= price <= gap["high"]:
            pts = max(pts, 6 if gap["status"] == "open" else 3)
            reasons.append(f"Price inside {gap['status']} FVG")
    return min(COMPONENT_MAX["zones"], pts), reasons or ["No active FVG/OB at price"]


def _score_premium_discount(analysis: dict, direction: str) -> tuple[int, list[str]]:
    pd_info = analysis["premium_discount"]
    zone = pd_info["zone"]
    if direction == "bullish" and zone == "discount":
        return COMPONENT_MAX["premium_discount"], [f"Price in discount ({pd_info['position']:.0%})"]
    if direction == "bearish" and zone == "premium":
        return COMPONENT_MAX["premium_discount"], [f"Price in premium ({pd_info['position']:.0%})"]
    if zone == "equilibrium":
        return 2, ["Price in equilibrium (mid-range)"]
    return 0, [f"Premium/discount misaligned ({zone})"]


def _score_session(analysis: dict) -> tuple[int, list[str]]:
    session = analysis.get("session") or {}
    weight = session.get("weight", 0.5)
    name = session.get("active") or analysis.get("killzone")
    if name:
        pts = int(COMPONENT_MAX["session"] * weight)
        return pts, [f"Session: {name} (weight {weight:.0%})"]
    return 1, ["Outside optimal session — reduced timing score"]


def _score_risk_filter(analysis: dict, spread_ok: bool, data_valid: bool) -> tuple[int, list[str]]:
    if not data_valid:
        return 0, ["Data validation failed"]
    if not spread_ok:
        return 0, ["Spread too wide"]
    return COMPONENT_MAX["risk_filter"], ["Risk filters passed"]


def _narrative_gate(analysis: dict, direction: str) -> tuple[bool, list[str]]:
    """Valid setup requires HTF allowance + sweep + structure shift + zone."""
    reasons: list[str] = []
    htf = analysis.get("htf_bias") or {}
    htf_dir = htf.get("direction", "neutral")
    label = analysis.get("higher_timeframe_bias", "NEUTRAL")

    if label in ("BEARISH",) and direction == "bullish":
        return False, ["HTF bearish — long setup invalid"]
    if label in ("BULLISH",) and direction == "bearish":
        return False, ["HTF bullish — short setup invalid"]

    confirmation = execution_confirmation(analysis, direction, max_bars=12)
    has_sweep = confirmation["sweep"] is not None
    has_shift = confirmation["event"] is not None and not any(
        reason for reason in confirmation["reasons"] if "sweep" not in reason.lower()
    )
    has_zone = active_entry_zone(analysis, direction) is not None

    if not has_sweep:
        reasons.append("Missing liquidity sweep narrative")
    if not has_shift:
        reasons.append("Missing recent displaced MSS/CHoCH after sweep")
    if not has_zone:
        reasons.append("Price has not refined into an aligned FVG/OB/breaker")

    ok = has_sweep and has_shift and has_zone
    return ok, reasons


def _institutional_direction(analysis: dict, votes: list) -> tuple[str | None, list[str]]:
    conflicts = []
    htf_direction = (analysis.get("htf_bias") or {}).get("direction")
    latest = latest_directional_event(analysis)
    structure_direction = latest.get("direction") if latest else None
    if htf_direction in ("bullish", "bearish"):
        if structure_direction and structure_direction != htf_direction:
            conflicts.append(f"Setup structure {structure_direction} conflicts with HTF {htf_direction}")
        return htf_direction, conflicts
    if structure_direction in ("bullish", "bearish"):
        return structure_direction, conflicts
    bullish = sum(weight for vote_direction, weight, *_ in votes if vote_direction == "bullish")
    bearish = sum(weight for vote_direction, weight, *_ in votes if vote_direction == "bearish")
    if max(bullish, bearish) == 0 or abs(bullish - bearish) < 1.0:
        return None, ["No decisive institutional direction"]
    return ("bullish" if bullish > bearish else "bearish"), conflicts


def compute_decision(
    analysis: dict,
    ml_signal: dict | None = None,
    strategy_mode: str = "both",
    *,
    spread_ok: bool = True,
    data_valid: bool = True,
    thresholds: SmcIctThresholds | None = None,
) -> dict:
    """Score-based decision: BUY_BIAS / SELL_BIAS / WAIT / NO_TRADE."""
    mode = normalize_strategy_mode(strategy_mode)
    symbol = analysis["symbol"]
    interval = analysis.get("interval", "60min")
    trading_style = analysis.get("trading_style", "intraday")
    decimals = 3 if symbol.upper().endswith("JPY") else 5
    if thresholds is None:
        thresholds = resolve_thresholds_model(symbol, interval, trading_style)

    votes = _collect_votes(analysis, strategy_mode=mode)
    bull_score_v = sum(w for d, w, _, _ in votes if d == "bullish")
    bear_score_v = sum(w for d, w, _, _ in votes if d == "bearish")
    direction, direction_conflicts = _institutional_direction(analysis, votes)
    if direction is None:
        direction = "bullish" if bull_score_v > bear_score_v else "bearish"

    components: dict[str, int] = {}
    reasoning: list[str] = []
    invalid_reasons: list[str] = []
    vetoes: list[str] = []
    if direction_conflicts:
        invalid_reasons.extend(direction_conflicts)
        vetoes.extend(f"VETO: {reason}" for reason in direction_conflicts)

    for name, scorer in (
        ("htf_bias", lambda: _score_htf_bias(analysis, direction)),
        ("structure", lambda: _score_structure(analysis, direction)),
        ("liquidity", lambda: _score_liquidity(analysis, direction)),
        ("displacement", lambda: _score_displacement(analysis, direction)),
        ("zones", lambda: _score_zones(analysis, direction)),
        ("premium_discount", lambda: _score_premium_discount(analysis, direction)),
        ("session", lambda: _score_session(analysis)),
        ("risk_filter", lambda: _score_risk_filter(analysis, spread_ok, data_valid)),
    ):
        pts, rs = scorer()
        components[name] = pts
        reasoning.extend(rs)

    total_score = sum(components.values())
    decision_cfg = thresholds.decision
    rr_cfg = thresholds.risk_reward
    pd_cfg = thresholds.premium_discount
    min_wait = decision_cfg.score_no_trade_below
    min_bias = decision_cfg.score_bias_minimum
    min_rr = min_risk_reward_for_style(thresholds, trading_style)
    min_conf_bias = decision_cfg.min_confidence_for_bias
    min_conf_strong = decision_cfg.min_confidence_for_strong_bias

    pd_info = analysis["premium_discount"]
    eq_low = pd_cfg.equilibrium_zone_low_percent / 100
    eq_high = pd_cfg.equilibrium_zone_high_percent / 100

    # ICT premium/discount alignment vetoes
    if direction == "bullish" and pd_info["zone"] != "discount":
        vetoes.append(
            f"VETO: longs only valid in discount; price is in {pd_info['zone']}"
        )
        invalid_reasons.append(f"Long setup invalid in {pd_info['zone']}")
    if direction == "bearish" and pd_info["zone"] != "premium":
        vetoes.append(
            f"VETO: shorts only valid in premium; price is in {pd_info['zone']}"
        )
        invalid_reasons.append(f"Short setup invalid in {pd_info['zone']}")

    if eq_low <= pd_info["position"] <= eq_high:
        has_sweep = bool(analysis.get("sweeps"))
        if not has_sweep:
            vetoes.append("VETO: price in mid-range equilibrium without sweep narrative")
            invalid_reasons.append("Price in middle of dealing range")

    narrative_ok, narrative_failures = _narrative_gate(analysis, direction)
    if not narrative_ok:
        for f in narrative_failures:
            vetoes.append(f"VETO: {f}")
            invalid_reasons.append(f)

    if analysis.get("htf_conflict", {}).get("conflict") and decision_cfg.force_no_trade_on_strong_conflict:
        vetoes.append("VETO: higher timeframe conflict")
        invalid_reasons.append("Timeframes conflict")

    if not spread_ok:
        vetoes.append("VETO: spread exceeds threshold")
        invalid_reasons.append("Spread too high")
    if not data_valid:
        vetoes.append("VETO: candle data invalid")
        invalid_reasons.append("Invalid or stale candle data")

    # Rule confidence only — meta ML gate runs in pipeline after this.
    ml_confidence = None
    rule_confidence = min(0.97, total_score / 100.0)
    final_confidence = rule_confidence

    min_final = settings.get_float("min_final_confidence", 0.55)
    if final_confidence < min_final:
        vetoes.append(f"VETO: confidence {final_confidence:.0%} below {min_final:.0%}")

    levels = _stop_and_target(analysis, direction, decimals)
    if rr_cfg.no_invalidation_force_no_trade and not levels.get("stop_loss"):
        vetoes.append("VETO: no invalidation price")
        invalid_reasons.append("No invalidation level")
    if rr_cfg.no_target_force_no_trade and not levels.get("take_profit"):
        vetoes.append("VETO: no target liquidity")
        invalid_reasons.append("No target liquidity")
    rr = levels.get("risk_reward")
    if rr is not None and rr < min_rr:
        vetoes.append(f"VETO: risk/reward {rr} below {min_rr}")
        invalid_reasons.append(f"Risk/reward {rr} below minimum {min_rr}")
    if levels.get("stop_exceeds_cap"):
        vetoes.append("VETO: structural invalidation exceeds maximum stop distance")
        invalid_reasons.append("Protective structure is too far from entry")

    confirmation = execution_confirmation(analysis, direction, max_bars=8)
    execution_ok = bool(analysis.get("execution_confirmed", False) or confirmation["confirmed"])

    # Decision bands
    if vetoes or total_score < min_wait:
        if total_score >= min_wait * 0.8 and _detect_wait_setup(analysis, votes, direction, vetoes):
            action = ACTION_WAIT
        else:
            action = ACTION_NO_TRADE
            levels = {
                "entry": None, "stop_loss": None, "take_profit": None,
                "risk_reward": None, "sl_pips": None, "tp_pips": None,
                "sl_pct": None, "tp_pct": None, "stop_basis": None, "target_basis": None,
            }
    elif total_score < min_bias or not narrative_ok:
        action = ACTION_WAIT
    elif not execution_ok:
        action = ACTION_WAIT
        reasoning.append("Awaiting lower-TF confirmation: " + "; ".join(
            confirmation["reasons"] or ["aligned MSS/CHoCH"]
        ))
    else:
        action = ACTION_BUY if direction == "bullish" else ACTION_SELL

    if action in (ACTION_BUY, ACTION_SELL):
        if total_score >= 75:
            final_confidence = max(final_confidence, min_conf_strong)
        elif total_score >= min_bias:
            final_confidence = max(final_confidence, min_conf_bias)

    component_scores = {
        "htf_bias": components["htf_bias"] * 5,
        "structure": components["structure"] * 5,
        "liquidity": components["liquidity"] * (100 / 15),
        "displacement": components["displacement"] * (100 / 15),
        "zones": components["zones"] * 10,
        "session": components["session"] * 20,
        "risk_filter": components["risk_filter"] * 20,
    }

    return {
        "symbol": symbol,
        "strategy": mode,
        "action": action,
        "direction": direction if action != ACTION_NO_TRADE else None,
        "confidence": round(min(0.97, final_confidence), 4),
        "rule_confidence": round(rule_confidence, 4),
        "ml_confidence": round(ml_confidence, 4) if ml_confidence is not None else None,
        "score": total_score,
        "scores": {"bullish": round(bull_score_v, 2), "bearish": round(bear_score_v, 2)},
        "component_scores": component_scores,
        "weighted_score": float(total_score),
        "confluences": len([v for v in votes if v[0] == direction]),
        "killzone": analysis.get("killzone"),
        "premium_discount": pd_info,
        "reasoning": reasoning,
        "counter_signals": [],
        "vetoes": vetoes,
        "no_trade_reasons": invalid_reasons or [v.replace("VETO: ", "") for v in vetoes],
        "invalid_reasons": invalid_reasons,
        "invalidation_price": levels.get("stop_loss"),
        "target_liquidity": levels.get("take_profit"),
        "disclaimer": DISCLAIMER,
        "higher_timeframe_bias": analysis.get("higher_timeframe_bias"),
        "market_trend": _trend_label(analysis),
        "institutional_confirmation": confirmation,
        **levels,
    }
