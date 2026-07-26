"""Supporting price-action evidence for the institutional rule engine.

These detectors never produce a trade direction by themselves. Their weights
are intentionally bounded and are only consumed after SMC/ICT establishes a
directional narrative.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _metrics(row) -> tuple[float, float, float, float]:
    body = abs(float(row.Close) - float(row.Open))
    span = max(float(row.High) - float(row.Low), 1e-12)
    upper = float(row.High) - max(float(row.Open), float(row.Close))
    lower = min(float(row.Open), float(row.Close)) - float(row.Low)
    return body, span, upper, lower


def _add(found: list[dict], name: str, direction: str, weight: float) -> None:
    if not any(item["name"] == name and item["direction"] == direction for item in found):
        found.append({
            "name": name,
            "direction": direction,
            "weight": min(float(weight), 0.30),
            "role": "supporting",
        })


def detect_candlesticks(df: pd.DataFrame) -> list[dict]:
    if len(df) < 3:
        return []
    found: list[dict] = []
    first, previous, current = (df.iloc[-3], df.iloc[-2], df.iloc[-1])
    body, span, upper, lower = _metrics(current)
    prev_body, prev_span, _, _ = _metrics(previous)
    direction = "bullish" if current.Close > current.Open else "bearish"
    midpoint = (float(previous.Open) + float(previous.Close)) / 2

    if body / span <= 0.10:
        _add(found, "Doji", "neutral", 0.10)
        if lower / span >= 0.60 and upper / span <= 0.10:
            _add(found, "Dragonfly Doji", "bullish", 0.16)
        if upper / span >= 0.60 and lower / span <= 0.10:
            _add(found, "Gravestone Doji", "bearish", 0.16)
    elif body / span <= 0.30 and upper / span >= 0.25 and lower / span >= 0.25:
        _add(found, "Spinning Top", "neutral", 0.10)

    if lower >= max(body * 2, span * 0.55) and upper <= span * 0.15:
        _add(found, "Hammer", "bullish", 0.20)
        _add(found, "Pin Bar", "bullish", 0.18)
    if upper >= max(body * 2, span * 0.55) and lower <= span * 0.15:
        _add(found, "Inverted Hammer", "bullish", 0.18)
        _add(found, "Shooting Star", "bearish", 0.20)
        _add(found, "Pin Bar", "bearish", 0.18)

    if current.High < previous.High and current.Low > previous.Low:
        _add(found, "Inside Bar", "neutral", 0.10)
    if current.High > previous.High and current.Low < previous.Low:
        _add(found, "Outside Bar", direction, 0.16)
    if body / span >= 0.90:
        _add(found, "Marubozu", direction, 0.18)

    prev_bear = previous.Close < previous.Open
    curr_bull = current.Close > current.Open
    if prev_bear and curr_bull and current.Open <= previous.Close and current.Close >= previous.Open:
        _add(found, "Bullish Engulfing", "bullish", 0.24)
    if not prev_bear and not curr_bull and current.Open >= previous.Close and current.Close <= previous.Open:
        _add(found, "Bearish Engulfing", "bearish", 0.24)
    if body <= prev_body * 0.60 and max(current.Open, current.Close) < max(previous.Open, previous.Close) and min(current.Open, current.Close) > min(previous.Open, previous.Close):
        _add(found, "Bullish Harami" if curr_bull else "Bearish Harami", direction, 0.16)

    first_body, first_span, _, _ = _metrics(first)
    if first.Close < first.Open and prev_body <= first_body * 0.50 and curr_bull and current.Close >= (first.Open + first.Close) / 2:
        _add(found, "Morning Star", "bullish", 0.24)
    if first.Close > first.Open and prev_body <= first_body * 0.50 and not curr_bull and current.Close <= (first.Open + first.Close) / 2:
        _add(found, "Evening Star", "bearish", 0.24)

    last_three = df.tail(3)
    bodies = (last_three.Close - last_three.Open).abs()
    spans = (last_three.High - last_three.Low).replace(0, np.nan)
    strong = (bodies / spans >= 0.55).all()
    if strong and (last_three.Close > last_three.Open).all() and last_three.Close.is_monotonic_increasing:
        _add(found, "Three Soldiers", "bullish", 0.26)
    if strong and (last_three.Close < last_three.Open).all() and last_three.Close.is_monotonic_decreasing:
        _add(found, "Three Crows", "bearish", 0.26)

    atr = float((df.High - df.Low).tail(20).median())
    tweezer_tolerance = max(atr * 0.08, float(current.Close) * 0.00005)
    if abs(float(current.Low) - float(previous.Low)) <= tweezer_tolerance and prev_bear and curr_bull:
        _add(found, "Tweezer Bottom", "bullish", 0.18)
    if abs(float(current.High) - float(previous.High)) <= tweezer_tolerance and not prev_bear and not curr_bull:
        _add(found, "Tweezer Top", "bearish", 0.18)

    if prev_bear and curr_bull and current.Open <= previous.Low and midpoint < current.Close < previous.Open:
        _add(found, "Piercing Pattern", "bullish", 0.22)
    if not prev_bear and not curr_bull and current.Open >= previous.High and previous.Open < current.Close < midpoint:
        _add(found, "Dark Cloud Cover", "bearish", 0.22)
    return found


def _turning_points(values: pd.Series, order: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    array = values.to_numpy(dtype=float)
    highs, lows = [], []
    for index in range(order, len(array) - order):
        window = array[index - order:index + order + 1]
        if array[index] == window.max():
            highs.append((index, float(array[index])))
        if array[index] == window.min():
            lows.append((index, float(array[index])))
    return highs, lows


def _linear_slope(values: pd.Series) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values)), values.to_numpy(dtype=float), 1)[0])


def detect_chart_structures(df: pd.DataFrame) -> list[dict]:
    if len(df) < 20:
        return []
    recent = df.tail(100)
    found: list[dict] = []
    atr = max(float((recent.High - recent.Low).median()), 1e-12)
    tolerance = atr * 0.45
    swing_highs, swing_lows = _turning_points(recent.Close, order=2)

    def near(values):
        return max(values) - min(values) <= tolerance

    if len(swing_highs) >= 2 and near([value for _, value in swing_highs[-2:]]):
        _add(found, "Double Top", "bearish", 0.24)
    if len(swing_lows) >= 2 and near([value for _, value in swing_lows[-2:]]):
        _add(found, "Double Bottom", "bullish", 0.24)
    if len(swing_highs) >= 3 and near([value for _, value in swing_highs[-3:]]):
        _add(found, "Triple Top", "bearish", 0.27)
    if len(swing_lows) >= 3 and near([value for _, value in swing_lows[-3:]]):
        _add(found, "Triple Bottom", "bullish", 0.27)

    if len(swing_highs) >= 3:
        left, head, right = swing_highs[-3:]
        if head[1] > max(left[1], right[1]) + tolerance and abs(left[1] - right[1]) <= tolerance * 1.5:
            _add(found, "Head and Shoulders", "bearish", 0.28)
    if len(swing_lows) >= 3:
        left, head, right = swing_lows[-3:]
        if head[1] < min(left[1], right[1]) - tolerance and abs(left[1] - right[1]) <= tolerance * 1.5:
            _add(found, "Inverse Head and Shoulders", "bullish", 0.28)

    half = recent.tail(max(15, len(recent) // 2))
    high_slope = _linear_slope(half.High)
    low_slope = _linear_slope(half.Low)
    width_start = float((half.High - half.Low).head(5).mean())
    width_end = float((half.High - half.Low).tail(5).mean())
    slope_tolerance = atr / max(len(half), 1) * 0.35

    if high_slope > 0 and low_slope > 0 and abs(high_slope - low_slope) <= slope_tolerance:
        _add(found, "Ascending Channel", "bullish", 0.18)
    elif high_slope < 0 and low_slope < 0 and abs(high_slope - low_slope) <= slope_tolerance:
        _add(found, "Descending Channel", "bearish", 0.18)
    elif abs(high_slope) <= slope_tolerance and abs(low_slope) <= slope_tolerance:
        _add(found, "Rectangle", "neutral", 0.12)

    if width_end < width_start * 0.75:
        if high_slope < 0 < low_slope:
            _add(found, "Symmetrical Triangle", "neutral", 0.16)
        elif abs(high_slope) <= slope_tolerance and low_slope > 0:
            _add(found, "Ascending Triangle", "bullish", 0.18)
        elif high_slope < 0 and abs(low_slope) <= slope_tolerance:
            _add(found, "Descending Triangle", "bearish", 0.18)
        elif high_slope < 0 and low_slope < 0:
            _add(found, "Falling Wedge", "bullish", 0.20)
        elif high_slope > 0 and low_slope > 0:
            _add(found, "Rising Wedge", "bearish", 0.20)

    if len(recent) >= 30:
        impulse = float(recent.Close.iloc[-11] - recent.Close.iloc[-25])
        consolidation = float(recent.High.tail(10).max() - recent.Low.tail(10).min())
        prior_range = float(recent.High.iloc[-25:-10].max() - recent.Low.iloc[-25:-10].min())
        if prior_range and consolidation < prior_range * 0.55 and abs(impulse) > atr * 1.5:
            name = "Pennant" if width_end < width_start * 0.75 else "Flag"
            _add(found, name, "bullish" if impulse > 0 else "bearish", 0.20)

    if len(recent) >= 50:
        first_half = recent.Close.iloc[-50:-15]
        bottom_pos = int(np.argmin(first_half.to_numpy()))
        left = float(first_half.iloc[0])
        bottom = float(first_half.iloc[bottom_pos])
        right = float(first_half.iloc[-1])
        handle = recent.Close.tail(15)
        depth = min(left, right) - bottom
        if depth > atr * 2 and abs(left - right) <= depth * 0.35 and float(handle.min()) > bottom + depth * 0.55:
            _add(found, "Cup and Handle", "bullish", 0.22)
    return found


def detect_wyckoff_context(df: pd.DataFrame) -> list[dict]:
    if len(df) < 30:
        return []
    recent = df.tail(40)
    found: list[dict] = []
    prior = recent.iloc[:-1]
    current = recent.iloc[-1]
    volume = recent.Volume if "Volume" in recent.columns else pd.Series(0.0, index=recent.index)
    volume_ratio = float(current.get("Volume", 0)) / max(float(volume.iloc[:-1].median()), 1.0)
    range_high, range_low = float(prior.High.max()), float(prior.Low.min())
    if current.Low < range_low and current.Close > range_low:
        _add(found, "Wyckoff Spring", "bullish", 0.24)
    if current.High > range_high and current.Close < range_high:
        _add(found, "Wyckoff Upthrust", "bearish", 0.24)
    width = max(range_high - range_low, 1e-12)
    close_position = (float(current.Close) - range_low) / width
    trend = _linear_slope(recent.Close)
    if abs(trend) <= width / len(recent) * 0.15:
        if close_position <= 0.45 and volume_ratio >= 1.1:
            _add(found, "Wyckoff Accumulation", "bullish", 0.16)
        if close_position >= 0.55 and volume_ratio >= 1.1:
            _add(found, "Wyckoff Distribution", "bearish", 0.16)
    if volume_ratio >= 1.5:
        _add(found, "Wyckoff Volume Confirmation", "neutral", 0.10)
    return found


def analyze_patterns(df: pd.DataFrame) -> dict:
    candles = detect_candlesticks(df)
    structures = detect_chart_structures(df)
    wyckoff = detect_wyckoff_context(df)
    items = candles + structures + wyckoff
    bullish = sum(pattern["weight"] for pattern in items if pattern["direction"] == "bullish")
    bearish = sum(pattern["weight"] for pattern in items if pattern["direction"] == "bearish")
    return {
        "candlesticks": candles,
        "chart_structures": structures,
        "wyckoff": wyckoff,
        "bullish_support": bullish,
        "bearish_support": bearish,
    }
