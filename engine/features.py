# engine/features.py
"""Per-candle feature matrix for the on-demand ML model.

Unlike the legacy pipeline (one summary row per CSV), every candle
becomes a training sample: the features describe the SMC/ICT state at
that moment and the label is the direction of the forward move, so the
model learns from hundreds of samples of THIS pair's own history each
time a prediction is requested.
"""
import numpy as np
import pandas as pd

from engine import ict, smc

HORIZON = 6              # bars ahead used for the label
LABEL_ATR_FRACTION = 0.25  # move must exceed this * ATR to count as up/down
SWEEP_LOOKBACK = 20      # window defining the liquidity level being swept
SWEEP_RECENT = 6         # bars a sweep stays "recent"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def build_features(df: pd.DataFrame, swing_window: int = 3) -> pd.DataFrame:
    """Feature frame aligned to df.index (NaNs at the warm-up head)."""
    out = pd.DataFrame(index=df.index)
    close, high, low, open_ = df["Close"], df["High"], df["Low"], df["Open"]
    atr_series = smc.atr(df)
    atr_safe = atr_series.replace(0, np.nan)

    # Momentum / volatility
    for k in (1, 3, 6, 12):
        out[f"ret_{k}"] = close.pct_change(k)
    out["atr_norm"] = atr_series / close
    rng = (high - low).replace(0, np.nan)
    out["body_ratio"] = (close - open_).abs() / rng
    out["upper_wick"] = (high - close.where(close > open_, open_)) / rng
    out["lower_wick"] = (close.where(close < open_, open_) - low) / rng
    out["rsi_14"] = _rsi(close)
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    out["ema_diff"] = (ema10 - ema50) / close

    # Premium/discount from structure-derived dealing range (matches confluence)
    swings = smc.find_swings(df, swing_window)
    structure = smc.detect_structure(df, swings, swing_window, atr_series)
    out["pd_position"] = ict.pd_position_series(df, structure["events"])
    out["dist_high_20"] = (high.rolling(20, min_periods=5).max() - close) / atr_safe
    out["dist_low_20"] = (close - low.rolling(20, min_periods=5).min()) / atr_safe

    # Liquidity sweep state: wick through the prior N-bar extreme with a
    # close back inside (the valid ICT sweep), remembered for a few bars.
    prior_high = high.shift(1).rolling(SWEEP_LOOKBACK, min_periods=5).max()
    prior_low = low.shift(1).rolling(SWEEP_LOOKBACK, min_periods=5).min()
    buyside_sweep = ((high > prior_high) & (close < prior_high)).astype(float)
    sellside_sweep = ((low < prior_low) & (close > prior_low)).astype(float)
    out["buyside_sweep_recent"] = buyside_sweep.rolling(SWEEP_RECENT, min_periods=1).max()
    out["sellside_sweep_recent"] = sellside_sweep.rolling(SWEEP_RECENT, min_periods=1).max()

    # Displacement + session timing
    out["displacement"] = ict.displacement_flags(df, atr_series).astype(float)
    out["in_killzone"] = ict.killzone_flags(df).astype(float)

    # Market-structure state from close-confirmed BOS/CHoCH events
    trend = np.zeros(len(df))
    choch_flag = np.zeros(len(df))
    event_pos = np.full(len(df), -1.0)
    bos_pos = np.full(len(df), -1.0)
    choch_pos = np.full(len(df), -1.0)
    for ev in structure["events"]:
        sign = 1.0 if ev["direction"] == "bullish" else -1.0
        trend[ev["pos"]:] = sign
        choch_flag[ev["pos"]:] = 1.0 if ev["kind"] == "CHoCH" else 0.0
        event_pos[ev["pos"]:] = ev["pos"]
        if ev["kind"] == "BOS":
            bos_pos[ev["pos"]:] = ev["pos"]
        else:
            choch_pos[ev["pos"]:] = ev["pos"]
    bars_since = np.where(event_pos >= 0, np.arange(len(df)) - event_pos, 200.0)
    bars_since_bos = np.where(bos_pos >= 0, np.arange(len(df)) - bos_pos, 200.0)
    bars_since_choch = np.where(choch_pos >= 0, np.arange(len(df)) - choch_pos, 200.0)
    out["structure_trend"] = trend
    out["last_event_choch"] = choch_flag
    out["bars_since_structure"] = np.clip(bars_since, 0, 200)
    out["bars_since_bos"] = np.clip(bars_since_bos, 0, 200)
    out["bars_since_choch"] = np.clip(bars_since_choch, 0, 200)

    return out


def build_labels(df: pd.DataFrame, horizon: int = HORIZON) -> pd.Series:
    """3-class forward label: 'up' / 'down' / 'flat'.

    The move over the next `horizon` bars must exceed a fraction of ATR
    to count as directional — small drifts are 'flat', which keeps the
    model honest about no-trade conditions.
    """
    close = df["Close"]
    atr_norm = (smc.atr(df) / close).to_numpy()
    fwd_ret = (close.shift(-horizon) / close - 1).to_numpy()
    thr = LABEL_ATR_FRACTION * atr_norm

    labels = np.where(
        np.isnan(fwd_ret), None,
        np.where(fwd_ret > thr, "up", np.where(fwd_ret < -thr, "down", "flat")),
    )
    return pd.Series(labels, index=df.index, dtype="object")


def build_dataset(df: pd.DataFrame, horizon: int = HORIZON) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) aligned on df.index; y is None-labelled for the last
    `horizon` rows (they have features but no future yet — the final row
    is what the live prediction runs on)."""
    X = build_features(df)
    y = build_labels(df, horizon)
    return X, y
