# config/smc_ict_thresholds.py
"""Default SMC/ICT thresholds, presets, and pure resolution (no DB)."""
from __future__ import annotations

from typing import Any

from schemas.threshold_schema import (
    SmcIctThresholds,
    merge_threshold_patch,
    validate_threshold_config,
)

DEFAULT_THRESHOLDS: SmcIctThresholds = SmcIctThresholds()

# Pair tier presets (spread + swing distance)
PAIR_TIERS: dict[str, str] = {
    "EURUSD": "major",
    "GBPUSD": "major",
    "USDJPY": "major",
    "USDCHF": "major",
    "USDCAD": "major",
    "AUDUSD": "major",
    "NZDUSD": "major",
    "EURGBP": "minor",
    "EURJPY": "minor",
    "GBPJPY": "minor",
    "AUDJPY": "minor",
    "EURAUD": "minor",
    "EURCHF": "minor",
    "GBPCHF": "minor",
    "CADJPY": "minor",
    "NZDJPY": "minor",
}

PAIR_PRESETS: dict[str, dict[str, Any]] = {
    "major": {
        "spread": {
            "max_spread_pips_major": 2.0,
            "spread_warning_pips_major": 1.5,
        },
        "swing": {
            "min_swing_distance_pips_major": 10,
            "equal_high_low_tolerance_pips": 3,
        },
    },
    "minor": {
        "spread": {
            "max_spread_pips_minor": 3.5,
        },
        "swing": {
            "min_swing_distance_pips_minor": 4,
            "equal_high_low_tolerance_pips": 4,
        },
    },
    "exotic": {
        "spread": {
            "max_spread_pips_exotic": 8.0,
        },
        "swing": {
            "min_swing_distance_pips_minor": 6,
            "equal_high_low_tolerance_pips": 5,
        },
    },
}

TIMEFRAME_PRESETS: dict[str, dict[str, Any]] = {
    "1min": {
        "data_quality": {"stale_candle_max_minutes_m1": 3},
        "bos": {"min_bos_break_pips_m5": 1.5},
        "fvg": {"min_fvg_size_pips_m5": 1.0, "fvg_max_age_candles_m5": 40},
    },
    "5min": {
        "data_quality": {"stale_candle_max_minutes_m5": 10},
        "bos": {"min_bos_break_pips_m5": 2.0},
        "fvg": {"min_fvg_size_pips_m5": 1.5, "fvg_max_age_candles_m5": 50},
        "verification": {"min_move_for_up_down_pips_m5": 5},
    },
    "15min": {
        "data_quality": {"stale_candle_max_minutes_m15": 25},
        "bos": {"min_bos_break_pips_m15": 3.0},
        "fvg": {"min_fvg_size_pips_m15": 2.5, "fvg_max_age_candles_m15": 40},
        "verification": {"min_move_for_up_down_pips_m15": 8},
    },
    "30min": {
        "data_quality": {"stale_candle_max_minutes_m30": 45},
        "bos": {"min_bos_break_pips_m15": 3.5},
        "fvg": {"min_fvg_size_pips_m15": 3.0},
    },
    "60min": {
        "data_quality": {"stale_candle_max_minutes_h1": 90},
        "bos": {"min_bos_break_pips_h1": 5.0},
        "fvg": {"min_fvg_size_pips_h1": 5.0, "fvg_max_age_candles_h1": 30},
        "verification": {"min_move_for_up_down_pips_h1": 15},
    },
    "240min": {
        "data_quality": {"stale_candle_max_minutes_h1": 120},
        "bos": {"min_bos_break_pips_h1": 8.0},
        "fvg": {"min_fvg_size_pips_h1": 8.0},
    },
    "daily": {
        "data_quality": {"stale_candle_max_minutes_h1": 180},
        "bos": {"min_bos_break_pips_h1": 10.0},
        "fvg": {"min_fvg_size_pips_h1": 12.0},
        "verification": {"min_move_for_up_down_pips_h1": 30},
    },
}

STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "scalping": {
        "decision": {
            "min_confidence_for_bias": 0.65,
            "score_bias_minimum": 65,
            "conflict_penalty_minor": 12,
        },
        "risk_reward": {"min_risk_reward_scalp": 1.5},
        "spread": {"max_spread_pips_major": 1.5},
        "verification": {"min_move_for_up_down_pips_m5": 5},
        "news": {"medium_news_penalty": 15, "news_block_before_minutes": 45},
    },
    "intraday": {
        "decision": {
            "min_confidence_for_bias": 0.60,
            "score_bias_minimum": 60,
        },
        "risk_reward": {"min_risk_reward_intraday": 2.0},
        "spread": {"max_spread_pips_major": 2.0},
        "verification": {"min_move_for_up_down_pips_m15": 8},
    },
    "swing": {
        "decision": {
            "min_confidence_for_bias": 0.60,
            "score_bias_minimum": 58,
            "conflict_penalty_major": 20,
        },
        "risk_reward": {"min_risk_reward_swing": 2.5},
        "spread": {"max_spread_pips_major": 3.0},
        "verification": {"min_move_for_up_down_pips_h1": 30},
        "news": {"medium_news_penalty": 8},
    },
}


def _normalize_pair(pair: str) -> str:
    return (pair or "EURUSD").upper().replace("/", "").replace("_", "")


def _normalize_timeframe(timeframe: str) -> str:
    tf = (timeframe or "60min").strip().lower()
    aliases = {"1h": "60min", "4h": "240min", "d1": "daily", "1d": "daily", "m5": "5min", "m15": "15min", "h1": "60min"}
    return aliases.get(tf, tf)


def _normalize_style(trading_style: str) -> str:
    style = (trading_style or "intraday").strip().lower()
    if style in ("scalp", "scalping"):
        return "scalping"
    if style in ("swing", "position"):
        return "swing"
    return "intraday"


def _pair_tier(pair: str) -> str:
    sym = _normalize_pair(pair)
    if sym in PAIR_TIERS:
        return PAIR_TIERS[sym]
    if "JPY" in sym and sym not in PAIR_TIERS:
        return "minor"
    return "major"


def pair_tier(pair: str) -> str:
    return _pair_tier(pair)


def resolve_thresholds(
    pair: str,
    timeframe: str,
    trading_style: str,
    *,
    version_config: dict | SmcIctThresholds | None = None,
    override_patch: dict | None = None,
) -> SmcIctThresholds:
    """
    Pure merge: defaults → version → style → timeframe → pair tier → override patch.
    """
    sym = _normalize_pair(pair)
    tf = _normalize_timeframe(timeframe)
    style = _normalize_style(trading_style)

    base = DEFAULT_THRESHOLDS
    if version_config is not None:
        if isinstance(version_config, SmcIctThresholds):
            base = version_config
        else:
            base = merge_threshold_patch(DEFAULT_THRESHOLDS, version_config)

    tier = _pair_tier(sym)
    patches: list[dict] = []

    style_patch = STYLE_PRESETS.get(style, {})
    if style_patch:
        patches.append(style_patch)

    tf_patch = TIMEFRAME_PRESETS.get(tf, {})
    if tf_patch:
        patches.append(tf_patch)

    tier_patch = PAIR_PRESETS.get(tier, {})
    if tier_patch:
        patches.append(tier_patch)

    if override_patch:
        patches.append(override_patch)

    result = base
    for patch in patches:
        if patch:
            result = merge_threshold_patch(result, patch)
    return result
