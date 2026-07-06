"""Meta-labels: WILL_RULE_SIGNAL_WIN (TP before SL)."""
from __future__ import annotations

OUTCOME_TP_BEFORE_SL = "TP_BEFORE_SL"
OUTCOME_SL_BEFORE_TP = "SL_BEFORE_TP"
OUTCOME_NEUTRAL = "NEUTRAL"
OUTCOME_EXPIRED = "EXPIRED"

META_LABEL_WIN = 1
META_LABEL_LOSS = 0

EXCLUDED_ACTIONS = frozenset({"NO_TRADE", "WAIT_FOR_CONFIRMATION", "WAIT"})


def outcome_to_meta_label(outcome: str) -> int | None:
    if outcome == OUTCOME_TP_BEFORE_SL:
        return META_LABEL_WIN
    if outcome == OUTCOME_SL_BEFORE_TP:
        return META_LABEL_LOSS
    return None


def is_trainable_action(action: str) -> bool:
    return action.upper() not in EXCLUDED_ACTIONS


def evaluate_tp_sl_path(
    candles,
    *,
    direction: str,
    entry: float,
    tp: float | None,
    sl: float | None,
) -> tuple[str, float, float]:
    """Walk forward candles; return outcome, MFE, MAE."""
    if tp is None or sl is None or entry <= 0:
        return OUTCOME_NEUTRAL, 0.0, 0.0

    mfe = 0.0
    mae = 0.0
    bullish = direction in ("bullish", "BUY", "BUY_BIAS", "BUY")

    for _, row in candles.iterrows():
        high = float(row["High"])
        low = float(row["Low"])
        if bullish:
            mfe = max(mfe, high - entry)
            mae = max(mae, entry - low)
            sl_hit = low <= sl
            tp_hit = high >= tp
        else:
            mfe = max(mfe, entry - low)
            mae = max(mae, high - entry)
            sl_hit = high >= sl
            tp_hit = low <= tp

        if sl_hit and tp_hit:
            return OUTCOME_NEUTRAL, mfe, mae
        if sl_hit:
            return OUTCOME_SL_BEFORE_TP, mfe, mae
        if tp_hit:
            return OUTCOME_TP_BEFORE_SL, mfe, mae

    return OUTCOME_EXPIRED, mfe, mae
