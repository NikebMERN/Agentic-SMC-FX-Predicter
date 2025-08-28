import pandas as pd # type: ignore

def detect_fvg(df):
    fvg_list = []

    for i in range(1, len(df) - 1):
        # Get previous, current, next candle
        prev_candle = df.iloc[i - 1]
        curr_candle = df.iloc[i]
        next_candle = df.iloc[i + 1]

        # Bullish FVG condition
        if prev_candle['low'] > next_candle['high']:
            fvg_list.append({
                'timestamp': curr_candle['timestamp'],
                'type': 'bullish',
                'low_gap': next_candle['high'],
                'high_gap': prev_candle['low']
            })

        # Bearish FVG condition
        elif prev_candle['high'] < next_candle['low']:
            fvg_list.append({
                'timestamp': curr_candle['timestamp'],
                'type': 'bearish',
                'low_gap': prev_candle['high'],
                'high_gap': next_candle['low']
            })

    return pd.DataFrame(fvg_list)
