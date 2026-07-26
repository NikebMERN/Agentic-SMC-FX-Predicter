"""ML quality gate: blend rule confidence with meta-model P(win)."""
from __future__ import annotations

from engine.confluence import ACTION_NO_TRADE, ACTION_WAIT
from utils import settings

DEFAULT_RULE_WEIGHT = 0.55
DEFAULT_ML_WEIGHT = 0.45
NO_TRADE_THRESHOLD = 0.50
WAIT_THRESHOLD = 0.60
MAX_CONFIDENCE = 0.85
NO_MODEL_CAP = 0.70


def _weights() -> tuple[float, float]:
    rule_w = settings.get_float("ml_blend_rule_weight", DEFAULT_RULE_WEIGHT)
    ml_w = settings.get_float("ml_blend_ml_weight", DEFAULT_ML_WEIGHT)
    total = rule_w + ml_w
    if total <= 0:
        return DEFAULT_RULE_WEIGHT, DEFAULT_ML_WEIGHT
    return rule_w / total, ml_w / total


def _thresholds() -> tuple[float, float, float]:
    no_trade = settings.get_float("ml_downgrade_no_trade_below", NO_TRADE_THRESHOLD)
    wait = settings.get_float("ml_downgrade_wait_below", WAIT_THRESHOLD)
    cap = settings.get_float("ml_confidence_cap", MAX_CONFIDENCE)
    return no_trade, wait, cap


def apply_ml_gate(
    decision: dict,
    *,
    ml_probability: float | None,
    has_active_model: bool,
) -> dict:
    """Adjust action/confidence after rule engine; returns augmented decision."""
    rule_conf = float(decision.get("rule_confidence", decision.get("confidence", 0)))
    action = decision.get("action", ACTION_NO_TRADE)
    reasoning = list(decision.get("reasoning") or [])
    vetoes = list(decision.get("vetoes") or [])

    if ml_probability is None or not has_active_model:
        final_conf = min(rule_conf, NO_MODEL_CAP)
        reasoning.append(f"No active meta-model — confidence capped at {NO_MODEL_CAP:.0%}")
        out = dict(decision)
        out.update({
            "confidence": round(final_conf, 4),
            "final_confidence": round(final_conf, 4),
            "confidence_before_ml": round(rule_conf, 4),
            "meta_ml_probability": None,
            "ml_confidence": None,
        })
        return out

    rule_w, ml_w = _weights()
    no_trade_t, wait_t, cap = _thresholds()
    blended = rule_w * rule_conf + ml_w * ml_probability
    final_conf = min(cap, blended)

    reasoning.append(
        f"Meta-ML P(win)={ml_probability:.2f}; blend {rule_w:.0%} rule / {ml_w:.0%} ML → {final_conf:.0%}"
    )

    original_action = action
    if action not in (ACTION_NO_TRADE, ACTION_WAIT) and ml_probability < no_trade_t:
        final_conf = min(final_conf, no_trade_t)
        reasoning.append("ML quality is weak; rule action retained and confidence reduced")
    elif action not in (ACTION_NO_TRADE, ACTION_WAIT) and ml_probability < wait_t:
        final_conf = min(final_conf, wait_t)
        reasoning.append("ML quality is cautious; rule action retained")

    out = dict(decision)
    out.update({
        "action": action,
        "confidence": round(final_conf, 4),
        "final_confidence": round(final_conf, 4),
        "confidence_before_ml": round(rule_conf, 4),
        "meta_ml_probability": round(ml_probability, 4),
        "ml_confidence": round(ml_probability, 4),
        "rule_confidence": round(rule_conf, 4),
        "reasoning": reasoning,
        "vetoes": vetoes,
        "ml_gate_original_action": original_action,
    })
    return out
