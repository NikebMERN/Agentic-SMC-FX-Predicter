const SINGLE_TF_MODES = new Set(["5min", "15min", "30min", "60min"]);

/** Map stored review interval to Predict page mode selector. */
export function intervalToPredictMode(interval) {
  const iv = (interval || "60min").toLowerCase();
  return SINGLE_TF_MODES.has(iv) ? iv : "mtf";
}

/** Build router state to auto-run /analyze on the predict page. */
export function buildAutoAnalyzeState(review) {
  if (!review?.symbol) return null;
  return {
    autoAnalyze: {
      symbol: review.symbol.toUpperCase(),
      horizon: review.trading_style || review.horizon || "intraday",
      mode: intervalToPredictMode(review.interval),
      strategy: review.strategy_mode || "both",
    },
  };
}
