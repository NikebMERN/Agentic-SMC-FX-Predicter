# engine/candle_validator.py
"""Validate OHLC candle series before analysis (no lookahead, stale, spread)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine.risk_calc import pip_size_for
from config.smc_ict_thresholds import DEFAULT_THRESHOLDS, pair_tier
from schemas.threshold_schema import SmcIctThresholds, max_spread_pips_for_pair, stale_minutes_for_timeframe
from services.threshold_service import resolve_thresholds_model
from utils.config import DATA_TZ


def validate_candles(
    df: pd.DataFrame,
    symbol: str,
    interval: str = "60min",
    *,
    spread_pips: float | None = None,
    thresholds: SmcIctThresholds | None = None,
    trading_style: str = "intraday",
) -> dict:
    """Return {valid, warnings, errors, candle_count, last_candle_age_minutes}."""
    if thresholds is None:
        try:
            thresholds = resolve_thresholds_model(symbol, interval, trading_style)
        except Exception:
            thresholds = DEFAULT_THRESHOLDS
    min_candles = thresholds.data_quality.min_candles_required
    stale_max = stale_minutes_for_timeframe(thresholds, interval)
    max_spread = max_spread_pips_for_pair(thresholds, pair_tier(symbol))

    warnings: list[str] = []
    errors: list[str] = []

    if df is None or df.empty:
        return {
            "valid": False,
            "warnings": warnings,
            "errors": ["No candle data"],
            "candle_count": 0,
            "last_candle_age_minutes": None,
            "quality": {
                "duplicate_count": 0,
                "missing_value_count": 0,
                "gap_count": 0,
                "estimated_missing_candles": 0,
                "abnormal_movement_count": 0,
            },
        }

    n = len(df)
    if n < min_candles:
        errors.append(f"Insufficient candles: {n} < {min_candles} required")

    duplicate_count = int(df.index.duplicated().sum())
    if duplicate_count:
        errors.append(f"{duplicate_count} duplicate timestamp(s) in candle series")

    if not df.index.is_monotonic_increasing:
        errors.append("Timestamps are not monotonically increasing")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.isna().any():
        errors.append("Invalid candle timestamp values")

    missing_values = 0
    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns or df[col].isna().any():
            errors.append(f"Missing or NaN values in {col}")
            missing_values += int(df[col].isna().sum()) if col in df.columns else n
    if all(col in df.columns for col in ("Open", "High", "Low", "Close")):
        ohlc = df[["Open", "High", "Low", "Close"]]
        if not np.isfinite(ohlc.to_numpy(dtype=float)).all():
            errors.append("Non-finite OHLC values")
        if (ohlc <= 0).any().any():
            errors.append("Non-positive OHLC prices")
        invalid_highs = int((df["High"] < ohlc.max(axis=1)).sum())
        invalid_lows = int((df["Low"] > ohlc.min(axis=1)).sum())
        if invalid_highs:
            errors.append(f"{invalid_highs} candle(s) have invalid highs")
        if invalid_lows:
            errors.append(f"{invalid_lows} candle(s) have invalid lows")

    last_ts = df.index[-1]
    now = pd.Timestamp.now(tz=timezone.utc)
    if last_ts.tzinfo is None:
        last_utc = last_ts.tz_localize(
            DATA_TZ, ambiguous=False, nonexistent="shift_forward"
        ).tz_convert("UTC")
    else:
        last_utc = last_ts.tz_convert("UTC")
    age_min = (now - last_utc).total_seconds() / 60.0
    if age_min > stale_max:
        warnings.append(f"Last candle is {age_min:.0f} min old (stale threshold {stale_max:.0f} min)")

    if spread_pips is not None and spread_pips > max_spread:
        errors.append(f"Spread {spread_pips:.1f} pips exceeds max {max_spread:.1f} pips")

    # Gap check on median interval
    gap_count = 0
    missing_candle_estimate = 0
    if n >= 3 and isinstance(df.index, pd.DatetimeIndex):
        deltas = df.index.to_series().diff().dropna()
        if not deltas.empty:
            median = deltas.median()
            gaps = deltas[deltas > median * 2.5]
            gap_count = len(gaps)
            missing_candle_estimate = int(sum(max(0, round(delta / median) - 1) for delta in gaps))
            if gap_count:
                warnings.append(
                    f"{gap_count} timestamp gap(s), approximately "
                    f"{missing_candle_estimate} missing candle(s)"
                )

    abnormal_count = 0
    if "Close" in df.columns and n >= 20:
        returns = df["Close"].pct_change().abs().dropna()
        median_return = float(returns.median())
        mad = float((returns - median_return).abs().median())
        abnormal_threshold = max(0.05, median_return + 12 * max(mad, 1e-9))
        abnormal_count = int((returns > abnormal_threshold).sum())
        if abnormal_count:
            warnings.append(
                f"{abnormal_count} abnormal price movement(s) above "
                f"{abnormal_threshold:.2%}"
            )
        if (returns > 0.15).any():
            errors.append("Extreme price discontinuity above 15% detected")

    return {
        "valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
        "candle_count": n,
        "last_candle_age_minutes": round(age_min, 1),
        "quality": {
            "duplicate_count": duplicate_count,
            "missing_value_count": missing_values,
            "gap_count": gap_count,
            "estimated_missing_candles": missing_candle_estimate,
            "abnormal_movement_count": abnormal_count,
        },
    }


def estimate_spread_pips(symbol: str, bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or ask <= bid:
        return None
    pip = pip_size_for(symbol)
    return round((ask - bid) / pip, 2)
