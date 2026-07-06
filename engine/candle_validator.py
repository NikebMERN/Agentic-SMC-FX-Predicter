# engine/candle_validator.py
"""Validate OHLC candle series before analysis (no lookahead, stale, spread)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from engine.risk_calc import pip_size_for
from config.smc_ict_thresholds import pair_tier
from schemas.threshold_schema import SmcIctThresholds, max_spread_pips_for_pair, stale_minutes_for_timeframe
from services.threshold_service import resolve_thresholds_model


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
        thresholds = resolve_thresholds_model(symbol, interval, trading_style)
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
        }

    n = len(df)
    if n < min_candles:
        errors.append(f"Insufficient candles: {n} < {min_candles} required")

    if df.index.duplicated().any():
        errors.append("Duplicate timestamps in candle series")

    if not df.index.is_monotonic_increasing:
        errors.append("Timestamps are not monotonically increasing")

    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns or df[col].isna().any():
            errors.append(f"Missing or NaN values in {col}")
            break

    last_ts = df.index[-1]
    now = pd.Timestamp.now(tz=timezone.utc)
    if last_ts.tzinfo is None:
        last_utc = last_ts.tz_localize("UTC")
    else:
        last_utc = last_ts.tz_convert("UTC")
    age_min = (now - last_utc).total_seconds() / 60.0
    if age_min > stale_max:
        warnings.append(f"Last candle is {age_min:.0f} min old (stale threshold {stale_max:.0f} min)")

    if spread_pips is not None and spread_pips > max_spread:
        errors.append(f"Spread {spread_pips:.1f} pips exceeds max {max_spread:.1f} pips")

    # Gap check on median interval
    if n >= 3:
        deltas = df.index.to_series().diff().dropna()
        if not deltas.empty:
            median = deltas.median()
            gaps = deltas[deltas > median * 2.5]
            if len(gaps) > 3:
                warnings.append(f"{len(gaps)} large timestamp gaps detected")

    return {
        "valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
        "candle_count": n,
        "last_candle_age_minutes": round(age_min, 1),
    }


def estimate_spread_pips(symbol: str, bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or ask <= bid:
        return None
    pip = pip_size_for(symbol)
    return round((ask - bid) / pip, 2)
