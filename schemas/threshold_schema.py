# schemas/threshold_schema.py
"""Pydantic schema for SMC/ICT threshold configuration with min/max validation."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ThresholdValidationError(ValueError):
    """Raised when threshold config or patch fails validation."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


class DataQualityThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_candles_required: int = Field(200, ge=100, le=1000)
    preferred_candles_required: int = Field(500, ge=200, le=2000)
    use_only_completed_candles: bool = True
    stale_candle_max_minutes_m1: int = Field(3, ge=1, le=10)
    stale_candle_max_minutes_m5: int = Field(10, ge=3, le=20)
    stale_candle_max_minutes_m15: int = Field(25, ge=10, le=45)
    stale_candle_max_minutes_m30: int = Field(45, ge=20, le=90)
    stale_candle_max_minutes_h1: int = Field(90, ge=60, le=180)
    max_missing_candles_percent: float = Field(1.0, ge=0, le=5)
    max_duplicate_candles: int = Field(0, ge=0, le=3)
    min_data_quality_score: int = Field(90, ge=70, le=100)


class SpreadThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_spread_pips_major: float = Field(2.0, ge=0.5, le=5)
    max_spread_pips_minor: float = Field(3.5, ge=1, le=8)
    max_spread_pips_exotic: float = Field(8.0, ge=3, le=25)
    spread_warning_pips_major: float = Field(1.5, ge=0.5, le=4)
    spread_confidence_penalty: int = Field(10, ge=0, le=30)
    abnormal_spread_multiplier: float = Field(2.5, ge=1.5, le=5)
    min_move_must_exceed_spread_multiplier: float = Field(3.0, ge=1.5, le=6)


class VolatilityThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    atr_period: int = Field(14, ge=7, le=50)
    max_atr_spike_multiplier: float = Field(2.5, ge=1.5, le=5)
    low_volatility_penalty: int = Field(10, ge=0, le=30)
    high_volatility_penalty: int = Field(15, ge=0, le=40)
    displacement_atr_multiplier: float = Field(1.2, ge=0.8, le=3)
    strong_displacement_atr_multiplier: float = Field(1.8, ge=1.2, le=4)


class SwingThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    swing_lookback_left: int = Field(3, ge=2, le=10)
    swing_lookback_right: int = Field(3, ge=2, le=10)
    major_swing_lookback_left: int = Field(5, ge=3, le=20)
    major_swing_lookback_right: int = Field(5, ge=3, le=20)
    min_swing_distance_pips_major: float = Field(10, ge=3, le=50)
    min_swing_distance_pips_minor: float = Field(4, ge=1, le=20)
    min_swing_distance_atr_multiplier: float = Field(0.25, ge=0.1, le=1)
    max_swing_age_candles: int = Field(150, ge=30, le=500)
    equal_high_low_tolerance_pips: float = Field(3, ge=1, le=10)
    equal_high_low_min_touches: int = Field(2, ge=2, le=5)


class BosThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_bos_break_pips_m5: float = Field(2, ge=1, le=8)
    min_bos_break_pips_m15: float = Field(3, ge=1, le=12)
    min_bos_break_pips_h1: float = Field(5, ge=2, le=25)
    min_bos_break_atr_multiplier: float = Field(0.1, ge=0.05, le=0.5)
    bos_requires_candle_close: bool = True
    bos_max_reclaim_candles: int = Field(3, ge=1, le=6)
    bos_displacement_required: bool = True
    bos_confidence_base: int = Field(15, ge=5, le=30)
    bos_against_htf_penalty: int = Field(15, ge=5, le=40)


class ChochMssThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_choch_break_pips_m5: float = Field(1.5, ge=0.5, le=6)
    min_choch_break_pips_m15: float = Field(2.5, ge=1, le=10)
    min_choch_break_pips_h1: float = Field(4, ge=2, le=20)
    choch_requires_prior_trend: bool = True
    choch_requires_close: bool = True
    choch_needs_displacement: bool = True
    mss_must_follow_liquidity_sweep: bool = True
    max_candles_between_sweep_and_mss_m5: int = Field(12, ge=3, le=30)
    max_candles_between_sweep_and_mss_m15: int = Field(8, ge=2, le=20)
    choch_confidence_base: int = Field(15, ge=5, le=30)
    mss_confidence_base: int = Field(20, ge=5, le=35)
    choch_without_sweep_penalty: int = Field(8, ge=0, le=25)


class LiquidityThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_sweep_depth_pips_major: float = Field(2, ge=0.5, le=10)
    min_sweep_depth_atr_multiplier: float = Field(0.08, ge=0.03, le=0.4)
    sweep_requires_close_back_inside: bool = True
    max_sweep_rejection_candles: int = Field(3, ge=1, le=8)
    sweep_body_close_strength_percent: int = Field(50, ge=30, le=80)
    liquidity_level_max_age_candles: int = Field(200, ge=30, le=1000)
    previous_day_high_low_weight: int = Field(15, ge=5, le=30)
    previous_week_high_low_weight: int = Field(20, ge=5, le=35)
    equal_high_low_sweep_weight: int = Field(12, ge=5, le=25)
    failed_sweep_penalty: int = Field(20, ge=5, le=50)


class FvgThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_fvg_size_pips_m5: float = Field(1.5, ge=0.5, le=10)
    min_fvg_size_pips_m15: float = Field(2.5, ge=1, le=15)
    min_fvg_size_pips_h1: float = Field(5, ge=2, le=30)
    min_fvg_size_atr_multiplier: float = Field(0.08, ge=0.03, le=0.5)
    fvg_requires_displacement: bool = True
    max_fvg_fill_percent_for_valid: int = Field(50, ge=10, le=90)
    fvg_fully_filled_invalid: bool = True
    fvg_max_age_candles_m5: int = Field(50, ge=10, le=200)
    fvg_max_age_candles_m15: int = Field(40, ge=10, le=150)
    fvg_max_age_candles_h1: int = Field(30, ge=10, le=120)
    fvg_entry_inside_percent_min: int = Field(25, ge=0, le=50)
    fvg_entry_inside_percent_max: int = Field(75, ge=50, le=100)
    fvg_confidence_base: int = Field(10, ge=3, le=25)


class OrderBlockThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ob_requires_displacement: bool = True
    ob_requires_structure_break: bool = True
    max_order_block_size_atr_multiplier: float = Field(1.2, ge=0.5, le=3)
    max_order_block_size_pips_major: float = Field(20, ge=5, le=60)
    max_ob_mitigations_allowed: int = Field(2, ge=0, le=5)
    ob_invalid_close_beyond_percent: int = Field(100, ge=50, le=100)
    ob_max_age_candles_m15: int = Field(50, ge=10, le=200)
    ob_max_age_candles_h1: int = Field(40, ge=10, le=150)
    ob_confidence_base: int = Field(10, ge=3, le=25)
    fresh_ob_bonus: int = Field(5, ge=0, le=15)
    over_mitigated_ob_penalty: int = Field(15, ge=5, le=40)


class PremiumDiscountThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    premium_start_percent: int = Field(50, ge=40, le=60)
    discount_end_percent: int = Field(50, ge=40, le=60)
    deep_premium_percent: int = Field(70, ge=60, le=85)
    deep_discount_percent: int = Field(30, ge=15, le=40)
    equilibrium_zone_low_percent: int = Field(45, ge=40, le=49)
    equilibrium_zone_high_percent: int = Field(55, ge=51, le=60)
    avoid_equilibrium_entries: bool = True
    premium_discount_confidence_base: int = Field(10, ge=3, le=25)
    wrong_pd_zone_penalty: int = Field(15, ge=5, le=40)
    pd_alone_cannot_signal: bool = True


class SessionThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timezone: str = "America/New_York"
    asian_session_start: str = "18:00"
    asian_session_end: str = "00:00"
    london_killzone_start: str = "02:00"
    london_killzone_end: str = "05:00"
    ny_am_killzone_start: str = "07:00"
    ny_am_killzone_end: str = "10:00"
    ny_pm_killzone_start: str = "13:00"
    ny_pm_killzone_end: str = "15:00"
    session_bonus_london: int = Field(5, ge=0, le=15)
    session_bonus_ny_am: int = Field(7, ge=0, le=15)
    session_bonus_ny_pm: int = Field(4, ge=0, le=15)
    dead_session_penalty: int = Field(10, ge=0, le=30)
    session_alone_cannot_signal: bool = True


class RiskRewardThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_risk_reward_scalp: float = Field(1.5, ge=1, le=3)
    min_risk_reward_intraday: float = Field(2.0, ge=1.5, le=4)
    min_risk_reward_swing: float = Field(2.5, ge=1.5, le=5)
    max_stop_distance_atr_multiplier: float = Field(1.5, ge=0.5, le=4)
    min_stop_distance_pips_major: float = Field(3, ge=1, le=10)
    target_must_be_liquidity: bool = True
    no_invalidation_force_no_trade: bool = True
    no_target_force_no_trade: bool = True
    max_risk_score_allowed: int = Field(60, ge=30, le=90)


class DecisionThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    score_no_trade_below: int = Field(50, ge=30, le=60)
    score_wait_below: int = Field(60, ge=50, le=70)
    score_bias_minimum: int = Field(60, ge=50, le=75)
    score_strong_bias_minimum: int = Field(75, ge=65, le=90)
    min_confidence_for_bias: float = Field(0.6, ge=0.4, le=0.85)
    min_confidence_for_strong_bias: float = Field(0.75, ge=0.6, le=0.95)
    max_confidence_cap_without_backtest: float = Field(0.75, ge=0.6, le=0.9)
    conflict_penalty_minor: int = Field(10, ge=5, le=25)
    conflict_penalty_major: int = Field(25, ge=10, le=50)
    force_no_trade_on_strong_conflict: bool = True
    wait_for_confirmation_if_entry_missing: bool = True


class NewsThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    avoid_high_impact_news: bool = True
    news_block_before_minutes: int = Field(30, ge=5, le=120)
    news_block_after_minutes: int = Field(30, ge=5, le=180)
    medium_news_penalty: int = Field(10, ge=0, le=30)
    high_news_force_no_trade: bool = True
    unknown_news_calendar_penalty: int = Field(5, ge=0, le=20)


class VerificationThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_move_for_up_down_pips_m5: float = Field(5, ge=2, le=20)
    min_move_for_up_down_pips_m15: float = Field(8, ge=3, le=30)
    min_move_for_up_down_pips_h1: float = Field(15, ge=5, le=60)
    sideways_threshold_pips_m15: float = Field(5, ge=1, le=20)
    sideways_threshold_atr_multiplier: float = Field(0.25, ge=0.1, le=0.6)
    target_hit_before_invalidation_required: bool = True
    max_verification_delay_minutes: int = Field(10, ge=1, le=60)
    mfe_mae_tracking: bool = True
    no_trade_not_counted_as_loss: bool = True
    wait_not_counted_as_loss: bool = True


class TrainingThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_feedback_weight: float = Field(0.25, ge=0, le=0.5)
    market_verification_weight: float = Field(0.75, ge=0.5, le=1)
    conflict_requires_admin_review: bool = True
    min_training_label_quality: float = Field(0.8, ge=0.5, le=1)
    auto_approve_clean_records: bool = False
    min_predictions_before_model_stats: int = Field(100, ge=30, le=1000)
    min_predictions_before_pair_stats: int = Field(50, ge=20, le=500)
    max_user_feedback_delay_hours: int = Field(72, ge=1, le=168)
    late_feedback_penalty: float = Field(0.2, ge=0, le=0.8)
    admin_approval_required_for_training: bool = True

    @field_validator("market_verification_weight")
    @classmethod
    def weights_sum_valid(cls, v: float, info) -> float:
        uf = info.data.get("user_feedback_weight", 0.25)
        if abs(uf + v - 1.0) > 0.01:
            raise ValueError("user_feedback_weight + market_verification_weight must sum to 1.0")
        return v


class SmcIctThresholds(BaseModel):
    """Root threshold configuration for SMC/ICT analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_quality: DataQualityThresholds = Field(default_factory=DataQualityThresholds)
    spread: SpreadThresholds = Field(default_factory=SpreadThresholds)
    volatility: VolatilityThresholds = Field(default_factory=VolatilityThresholds)
    swing: SwingThresholds = Field(default_factory=SwingThresholds)
    bos: BosThresholds = Field(default_factory=BosThresholds)
    choch_mss: ChochMssThresholds = Field(default_factory=ChochMssThresholds)
    liquidity: LiquidityThresholds = Field(default_factory=LiquidityThresholds)
    fvg: FvgThresholds = Field(default_factory=FvgThresholds)
    order_block: OrderBlockThresholds = Field(default_factory=OrderBlockThresholds)
    premium_discount: PremiumDiscountThresholds = Field(default_factory=PremiumDiscountThresholds)
    session: SessionThresholds = Field(default_factory=SessionThresholds)
    risk_reward: RiskRewardThresholds = Field(default_factory=RiskRewardThresholds)
    decision: DecisionThresholds = Field(default_factory=DecisionThresholds)
    news: NewsThresholds = Field(default_factory=NewsThresholds)
    verification: VerificationThresholds = Field(default_factory=VerificationThresholds)
    training: TrainingThresholds = Field(default_factory=TrainingThresholds)


TF_KEY_MAP = {
    "1min": "M5",
    "3min": "M5",
    "5min": "M5",
    "15min": "M15",
    "30min": "M15",
    "60min": "H1",
    "240min": "H1",
    "daily": "H1",
    "day": "H1",
}


def get_tf_key(timeframe: str) -> Literal["M5", "M15", "H1"]:
    key = (timeframe or "60min").strip().lower()
    return TF_KEY_MAP.get(key, "H1")  # type: ignore[return-value]


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def validate_threshold_config(data: dict | None) -> SmcIctThresholds:
    try:
        return SmcIctThresholds.model_validate(data or {})
    except ValidationError as exc:
        raise ThresholdValidationError(
            "Invalid threshold configuration",
            errors=exc.errors(),
        ) from exc


def merge_threshold_patch(base: SmcIctThresholds, patch: dict) -> SmcIctThresholds:
    merged = _deep_merge(base.model_dump(), patch)
    return validate_threshold_config(merged)


def stale_minutes_for_timeframe(thresholds: SmcIctThresholds, timeframe: str) -> int:
    dq = thresholds.data_quality
    tf = (timeframe or "60min").lower()
    mapping = {
        "1min": dq.stale_candle_max_minutes_m1,
        "5min": dq.stale_candle_max_minutes_m5,
        "15min": dq.stale_candle_max_minutes_m15,
        "30min": dq.stale_candle_max_minutes_m30,
        "60min": dq.stale_candle_max_minutes_h1,
        "240min": dq.stale_candle_max_minutes_h1 * 2,
        "daily": dq.stale_candle_max_minutes_h1 * 4,
    }
    return mapping.get(tf, dq.stale_candle_max_minutes_m15)


def min_bos_break_pips(thresholds: SmcIctThresholds, timeframe: str) -> float:
    tf = get_tf_key(timeframe)
    bos = thresholds.bos
    if tf == "M5":
        return bos.min_bos_break_pips_m5
    if tf == "M15":
        return bos.min_bos_break_pips_m15
    return bos.min_bos_break_pips_h1


def min_fvg_size_pips(thresholds: SmcIctThresholds, timeframe: str) -> float:
    tf = get_tf_key(timeframe)
    fvg = thresholds.fvg
    if tf == "M5":
        return fvg.min_fvg_size_pips_m5
    if tf == "M15":
        return fvg.min_fvg_size_pips_m15
    return fvg.min_fvg_size_pips_h1


def min_risk_reward_for_style(thresholds: SmcIctThresholds, trading_style: str) -> float:
    style = (trading_style or "intraday").lower()
    rr = thresholds.risk_reward
    if style == "scalping":
        return rr.min_risk_reward_scalp
    if style == "swing":
        return rr.min_risk_reward_swing
    return rr.min_risk_reward_intraday


def max_spread_pips_for_pair(thresholds: SmcIctThresholds, pair_tier: str) -> float:
    tier = (pair_tier or "major").lower()
    sp = thresholds.spread
    if tier == "exotic":
        return sp.max_spread_pips_exotic
    if tier == "minor":
        return sp.max_spread_pips_minor
    return sp.max_spread_pips_major


def thresholds_to_legacy_flat(thresholds: SmcIctThresholds, timeframe: str = "60min", trading_style: str = "intraday") -> dict[str, Any]:
    """Backward-compatible flat dict for gradual migration."""
    return {
        "minCandlesRequired": thresholds.data_quality.min_candles_required,
        "minBosBreakPips": min_bos_break_pips(thresholds, timeframe),
        "minChochBreakPips": thresholds.choch_mss.min_choch_break_pips_m15,
        "minFvgSizePips": min_fvg_size_pips(thresholds, timeframe),
        "minDisplacementAtrMultiplier": thresholds.volatility.displacement_atr_multiplier,
        "maxSpreadPips": thresholds.spread.max_spread_pips_major,
        "minRiskReward": min_risk_reward_for_style(thresholds, trading_style),
        "minConfidenceForBias": thresholds.decision.min_confidence_for_bias,
        "minConfidenceForStrongBias": thresholds.decision.min_confidence_for_strong_bias,
        "equalHighLowTolerancePips": thresholds.swing.equal_high_low_tolerance_pips,
        "staleCandleMaxMinutes": stale_minutes_for_timeframe(thresholds, timeframe),
        "minScoreForBias": thresholds.decision.score_bias_minimum,
        "minScoreForWait": thresholds.decision.score_no_trade_below,
        "equilibriumLow": thresholds.premium_discount.equilibrium_zone_low_percent / 100,
        "equilibriumHigh": thresholds.premium_discount.equilibrium_zone_high_percent / 100,
    }
