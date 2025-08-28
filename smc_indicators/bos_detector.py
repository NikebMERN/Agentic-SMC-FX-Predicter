import pandas as pd  # type: ignore

def infer_trend(swings_df: pd.DataFrame) -> str:
    highs = swings_df[swings_df['type'] == 'high']
    lows = swings_df[swings_df['type'] == 'low']

    if len(highs) >= 2 and highs.iloc[-1]['price'] > highs.iloc[-2]['price']:
        return 'bullish'
    elif len(lows) >= 2 and lows.iloc[-1]['price'] < lows.iloc[-2]['price']:
        return 'bearish'
    else:
        return 'sideways'


def detect_bos(swings_df: pd.DataFrame, candles_df: pd.DataFrame):
    candles_df.columns = candles_df.columns.str.lower()
    bos_events = []

    if len(swings_df) < 3:
        return bos_events

    trend = infer_trend(swings_df)
    print(f"[INFO] Detected trend: {trend}")

    for i in range(2, len(swings_df)):
        current = swings_df.iloc[i]
        prev = swings_df.iloc[i - 1]

        # Get integer positions of the current and previous swings
        prev_idx = candles_df.index.get_loc(prev.name)
        curr_idx = candles_df.index.get_loc(current.name)

        # Bullish BOS
        if trend == 'bullish' and prev['type'] == 'high' and current['type'] == 'low':
            high_range = candles_df.iloc[prev_idx:curr_idx + 1]['high']
            if not high_range.empty:
                max_high = high_range.max()
                if max_high > prev['price']:
                    break_idx = high_range.idxmax()
                    bos_events.append({
                        'type': 'bullish_bos',
                        'broken_swing_idx': prev_idx,
                        'break_candle_idx': break_idx,
                        'price': max_high,
                        'timestamp': candles_df.loc[break_idx, 'timestamp'] if 'timestamp' in candles_df.columns else break_idx
                    })

        # Bearish BOS
        elif trend == 'bearish' and prev['type'] == 'low' and current['type'] == 'high':
            low_range = candles_df.iloc[prev_idx:curr_idx + 1]['low']
            if not low_range.empty:
                min_low = low_range.min()
                if min_low < prev['price']:
                    break_idx = low_range.idxmin()
                    bos_events.append({
                        'type': 'bearish_bos',
                        'broken_swing_idx': prev_idx,
                        'break_candle_idx': break_idx,
                        'price': min_low,
                        'timestamp': candles_df.loc[break_idx, 'timestamp'] if 'timestamp' in candles_df.columns else break_idx
                    })

        # Sideways logic
        elif trend == 'sideways':
            if prev['type'] == 'high' and current['type'] == 'low':
                high_range = candles_df.iloc[prev_idx:curr_idx + 1]['high']
                if not high_range.empty:
                    max_high = high_range.max()
                    if abs(max_high - prev['price']) / prev['price'] < 0.001:
                        bos_events.append({
                            'type': 'sideways',
                            'swing_type': 'high',
                            'reference_idx': prev_idx,
                            'range_high': max_high,
                            'range_low': candles_df.iloc[prev_idx:curr_idx + 1]['low'].min(),
                            'timestamp': candles_df.iloc[curr_idx]['timestamp'] if 'timestamp' in candles_df.columns else curr_idx
                        })

            elif prev['type'] == 'low' and current['type'] == 'high':
                low_range = candles_df.iloc[prev_idx:curr_idx + 1]['low']
                if not low_range.empty:
                    min_low = low_range.min()
                    if abs(min_low - prev['price']) / prev['price'] < 0.002:
                        bos_events.append({
                            'type': 'sideways',
                            'swing_type': 'low',
                            'reference_idx': prev_idx,
                            'range_low': min_low,
                            'range_high': candles_df.iloc[prev_idx:curr_idx + 1]['high'].max(),
                            'timestamp': candles_df.iloc[curr_idx]['timestamp'] if 'timestamp' in candles_df.columns else curr_idx
                        })

    return bos_events
