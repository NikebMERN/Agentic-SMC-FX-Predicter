"""Compare candidate vs active model for auto-promotion."""
from __future__ import annotations

import json
import math

from utils import settings

DEFAULT_GATE = {
    "min_walk_forward_score": 0.45,
    "min_precision": 0.50,
    "min_f1": 0.40,
    "max_brier_score": 0.30,
    "min_samples": 50,
    "min_improvement_f1": 0.02,
    "min_improvement_precision": 0.01,
    "min_profit_factor": 1.10,
    "min_expectancy": 0.05,
    "min_sharpe_ratio": 0.25,
    "max_drawdown": 20.0,
    "min_win_rate_improvement": 0.01,
}


def get_promotion_gate() -> dict:
    raw = settings.get("promotion_gate_json")
    if not raw:
        return dict(DEFAULT_GATE)
    try:
        data = json.loads(raw)
        merged = dict(DEFAULT_GATE)
        merged.update(data)
        return merged
    except json.JSONDecodeError:
        return dict(DEFAULT_GATE)


def promotion_enabled() -> bool:
    raw = settings.get("model_promotion_enabled", "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def evaluate_promotion(
    candidate_metrics: dict,
    active_metrics: dict | None = None,
    *,
    gate: dict | None = None,
) -> dict:
    gate = gate or get_promotion_gate()
    reasons: list[str] = []
    passed = True

    for key, min_val in (
        ("walk_forward_score", gate["min_walk_forward_score"]),
        ("precision", gate["min_precision"]),
        ("f1", gate["min_f1"]),
    ):
        val = candidate_metrics.get(key)
        if val is None or val < min_val:
            passed = False
            reasons.append(f"{key} {val} < {min_val}")

    brier = candidate_metrics.get("brier_score")
    if brier is not None and brier > gate["max_brier_score"]:
        passed = False
        reasons.append(f"brier_score {brier} > {gate['max_brier_score']}")

    samples = candidate_metrics.get("samples") or candidate_metrics.get("total_signals", 0)
    if samples < gate["min_samples"]:
        passed = False
        reasons.append(f"samples {samples} < {gate['min_samples']}")

    for key, minimum in (
        ("profit_factor", gate["min_profit_factor"]),
        ("expectancy", gate["min_expectancy"]),
        ("sharpe_ratio", gate["min_sharpe_ratio"]),
    ):
        value = candidate_metrics.get(key)
        if value is None or value < minimum:
            passed = False
            reasons.append(f"{key} {value} < {minimum}")
    drawdown = candidate_metrics.get("max_drawdown")
    if drawdown is None or drawdown > gate["max_drawdown"]:
        passed = False
        reasons.append(f"max_drawdown {drawdown} > {gate['max_drawdown']}")

    if active_metrics:
        for key, min_imp in (
            ("f1", gate["min_improvement_f1"]),
            ("precision", gate["min_improvement_precision"]),
        ):
            cand = candidate_metrics.get(key, 0) or 0
            active = active_metrics.get(key, 0) or 0
            if cand < active + min_imp:
                passed = False
                reasons.append(f"{key} improvement {cand - active:.3f} < {min_imp}")
        win_rate_gain = (candidate_metrics.get("win_rate") or 0) - (active_metrics.get("win_rate") or 0)
        if win_rate_gain < gate["min_win_rate_improvement"]:
            passed = False
            reasons.append(
                f"win_rate improvement {win_rate_gain:.3f} < {gate['min_win_rate_improvement']}"
            )
        candidate_n = int(candidate_metrics.get("total_signals") or candidate_metrics.get("samples") or 0)
        active_n = int(active_metrics.get("total_signals") or active_metrics.get("samples") or 0)
        candidate_rate = float(candidate_metrics.get("win_rate") or 0)
        active_rate = float(active_metrics.get("win_rate") or 0)
        if candidate_n >= 30 and active_n >= 30:
            pooled = (
                candidate_rate * candidate_n + active_rate * active_n
            ) / (candidate_n + active_n)
            standard_error = math.sqrt(max(
                pooled * (1 - pooled) * (1 / candidate_n + 1 / active_n), 1e-12
            ))
            z_score = (candidate_rate - active_rate) / standard_error
            if z_score < 1.645:
                passed = False
                reasons.append(f"win-rate improvement not statistically significant (z={z_score:.2f})")

    if not promotion_enabled() and passed:
        reasons.append("promotion disabled by feature flag")
        passed = False

    return {
        "passed": passed,
        "reasons": reasons,
        "gate": gate,
    }
