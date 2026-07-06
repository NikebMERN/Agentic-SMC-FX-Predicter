# tests/test_threshold_resolution.py
"""Pure resolution order: defaults → version → style → TF → pair tier → override."""
from config.smc_ict_thresholds import DEFAULT_THRESHOLDS, resolve_thresholds
from schemas.threshold_schema import merge_threshold_patch


def test_style_preset_scalping_confidence():
    t = resolve_thresholds("EURUSD", "60min", "scalping")
    assert t.decision.min_confidence_for_bias >= 0.65


def test_timeframe_preset_m5_bos():
    t = resolve_thresholds("EURUSD", "5min", "intraday")
    assert t.bos.min_bos_break_pips_m5 == 2.0


def test_version_config_overrides_defaults():
    version = {"data_quality": {"min_candles_required": 250}}
    t = resolve_thresholds("EURUSD", "60min", "intraday", version_config=version)
    assert t.data_quality.min_candles_required == 250


def test_override_patch_wins():
    version = {"decision": {"score_bias_minimum": 70}}
    override = {"decision": {"score_bias_minimum": 72}}
    t = resolve_thresholds(
        "EURUSD", "60min", "intraday",
        version_config=version, override_patch=override,
    )
    assert t.decision.score_bias_minimum == 72


def test_swing_rr_higher_than_scalp():
    scalp = resolve_thresholds("EURUSD", "60min", "scalping")
    swing = resolve_thresholds("EURUSD", "60min", "swing")
    assert swing.risk_reward.min_risk_reward_swing >= scalp.risk_reward.min_risk_reward_scalp
