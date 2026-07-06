/** Editable SMC/ICT threshold fields grouped for the admin editor. */
export const THRESHOLD_SECTIONS = [
  {
    id: "data_quality",
    label: "Data quality",
    description: "Candle history, staleness, and data validation gates.",
    fields: [
      { key: "min_candles_required", label: "Min candles required", type: "number", min: 100, max: 1000, step: 1 },
      { key: "preferred_candles_required", label: "Preferred candles", type: "number", min: 200, max: 2000, step: 1 },
      { key: "use_only_completed_candles", label: "Use only completed candles", type: "boolean" },
      { key: "stale_candle_max_minutes_m5", label: "Stale limit M5 (min)", type: "number", min: 3, max: 20, step: 1 },
      { key: "stale_candle_max_minutes_m15", label: "Stale limit M15 (min)", type: "number", min: 10, max: 45, step: 1 },
      { key: "stale_candle_max_minutes_h1", label: "Stale limit H1 (min)", type: "number", min: 60, max: 180, step: 1 },
      { key: "min_data_quality_score", label: "Min data quality score", type: "number", min: 70, max: 100, step: 1 },
    ],
  },
  {
    id: "spread",
    label: "Spread",
    description: "Spread limits and abnormal spread handling.",
    fields: [
      { key: "max_spread_pips_major", label: "Max spread majors (pips)", type: "number", min: 0.5, max: 5, step: 0.1 },
      { key: "max_spread_pips_minor", label: "Max spread minors (pips)", type: "number", min: 1, max: 8, step: 0.1 },
      { key: "spread_warning_pips_major", label: "Spread warning majors", type: "number", min: 0.5, max: 4, step: 0.1 },
      { key: "abnormal_spread_multiplier", label: "Abnormal spread multiplier", type: "number", min: 1.5, max: 5, step: 0.1 },
    ],
  },
  {
    id: "decision",
    label: "Decision bands",
    description: "Score thresholds for NO_TRADE, WAIT, and bias signals.",
    fields: [
      { key: "score_no_trade_below", label: "NO_TRADE below score", type: "number", min: 30, max: 60, step: 1 },
      { key: "score_wait_below", label: "WAIT below score", type: "number", min: 50, max: 70, step: 1 },
      { key: "score_bias_minimum", label: "Bias minimum score", type: "number", min: 50, max: 75, step: 1 },
      { key: "score_strong_bias_minimum", label: "Strong bias minimum", type: "number", min: 65, max: 90, step: 1 },
      { key: "min_confidence_for_bias", label: "Min confidence for bias", type: "number", min: 0.4, max: 0.85, step: 0.01 },
      { key: "min_confidence_for_strong_bias", label: "Min confidence strong bias", type: "number", min: 0.6, max: 0.95, step: 0.01 },
      { key: "force_no_trade_on_strong_conflict", label: "Force NO_TRADE on HTF conflict", type: "boolean" },
      { key: "wait_for_confirmation_if_entry_missing", label: "WAIT if entry missing", type: "boolean" },
    ],
  },
  {
    id: "risk_reward",
    label: "Risk / reward",
    description: "RR minimums and invalidation rules.",
    fields: [
      { key: "min_risk_reward_scalp", label: "Min RR scalping", type: "number", min: 1, max: 3, step: 0.1 },
      { key: "min_risk_reward_intraday", label: "Min RR intraday", type: "number", min: 1.5, max: 4, step: 0.1 },
      { key: "min_risk_reward_swing", label: "Min RR swing", type: "number", min: 1.5, max: 5, step: 0.1 },
      { key: "no_invalidation_force_no_trade", label: "No invalidation → NO_TRADE", type: "boolean" },
      { key: "no_target_force_no_trade", label: "No target → NO_TRADE", type: "boolean" },
      { key: "target_must_be_liquidity", label: "Target must be liquidity", type: "boolean" },
    ],
  },
  {
    id: "bos",
    label: "BOS",
    description: "Break of structure detection thresholds.",
    fields: [
      { key: "min_bos_break_pips_m5", label: "Min BOS break M5 (pips)", type: "number", min: 1, max: 8, step: 0.5 },
      { key: "min_bos_break_pips_m15", label: "Min BOS break M15 (pips)", type: "number", min: 1, max: 12, step: 0.5 },
      { key: "min_bos_break_pips_h1", label: "Min BOS break H1 (pips)", type: "number", min: 2, max: 25, step: 0.5 },
      { key: "bos_requires_candle_close", label: "BOS requires candle close", type: "boolean" },
      { key: "bos_displacement_required", label: "BOS displacement required", type: "boolean" },
    ],
  },
  {
    id: "choch_mss",
    label: "CHoCH / MSS",
    fields: [
      { key: "min_choch_break_pips_m15", label: "Min CHoCH M15 (pips)", type: "number", min: 1, max: 10, step: 0.5 },
      { key: "mss_must_follow_liquidity_sweep", label: "MSS must follow sweep", type: "boolean" },
      { key: "choch_requires_close", label: "CHoCH requires close", type: "boolean" },
    ],
  },
  {
    id: "liquidity",
    label: "Liquidity",
    fields: [
      { key: "min_sweep_depth_pips_major", label: "Min sweep depth (pips)", type: "number", min: 0.5, max: 10, step: 0.5 },
      { key: "sweep_requires_close_back_inside", label: "Sweep requires close back inside", type: "boolean" },
      { key: "failed_sweep_penalty", label: "Failed sweep penalty", type: "number", min: 5, max: 50, step: 1 },
    ],
  },
  {
    id: "fvg",
    label: "Fair value gaps",
    fields: [
      { key: "min_fvg_size_pips_m5", label: "Min FVG M5 (pips)", type: "number", min: 0.5, max: 10, step: 0.5 },
      { key: "min_fvg_size_pips_m15", label: "Min FVG M15 (pips)", type: "number", min: 1, max: 15, step: 0.5 },
      { key: "fvg_requires_displacement", label: "FVG requires displacement", type: "boolean" },
      { key: "fvg_fully_filled_invalid", label: "Fully filled FVG invalid", type: "boolean" },
    ],
  },
  {
    id: "verification",
    label: "Verification",
    fields: [
      { key: "min_move_for_up_down_pips_m15", label: "Min move M15 (pips)", type: "number", min: 3, max: 30, step: 1 },
      { key: "sideways_threshold_atr_multiplier", label: "Sideways ATR multiplier", type: "number", min: 0.1, max: 0.6, step: 0.05 },
      { key: "no_trade_not_counted_as_loss", label: "NO_TRADE not counted as loss", type: "boolean" },
      { key: "wait_not_counted_as_loss", label: "WAIT not counted as loss", type: "boolean" },
    ],
  },
  {
    id: "training",
    label: "Training",
    fields: [
      { key: "user_feedback_weight", label: "User feedback weight", type: "number", min: 0, max: 0.5, step: 0.05 },
      { key: "market_verification_weight", label: "Market verification weight", type: "number", min: 0.5, max: 1, step: 0.05 },
      { key: "min_training_label_quality", label: "Min label quality", type: "number", min: 0.5, max: 1, step: 0.05 },
      { key: "admin_approval_required_for_training", label: "Admin approval required", type: "boolean" },
      { key: "auto_approve_clean_records", label: "Auto-approve clean records", type: "boolean" },
    ],
  },
];

export const TRADING_STYLES = ["scalping", "intraday", "swing"];

export const INTERVALS = ["5min", "15min", "30min", "60min", "240min", "daily"];

export const PREVIEW_SUMMARY_PATHS = [
  ["decision", "score_bias_minimum", "Bias min score"],
  ["decision", "min_confidence_for_bias", "Min confidence"],
  ["risk_reward", "min_risk_reward_intraday", "Min RR intraday"],
  ["spread", "max_spread_pips_major", "Max spread major"],
  ["data_quality", "min_candles_required", "Min candles"],
  ["bos", "min_bos_break_pips_h1", "Min BOS H1"],
];
