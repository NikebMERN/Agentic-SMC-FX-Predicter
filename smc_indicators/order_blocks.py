import pandas as pd # type: ignore

def detect_order_blocks(df):
    bullish_obs = []
    bearish_obs = []

    for i in range(2, len(df) - 2):
        current = df.iloc[i]
        next1 = df.iloc[i + 1]
        next2 = df.iloc[i + 2]

        # Bullish OB: Last bearish candle before 2+ bullish candles
        if current['open'] > current['close'] and \
           next1['close'] > next1['open'] and next2['close'] > next2['open'] and \
           next2['close'] > current['high']:
            bullish_obs.append({
                'timestamp': current['timestamp'],
                'type': 'bullish',
                'price': current['high']
            })

        # Bearish OB: Last bullish candle before 2+ bearish candles
        elif current['close'] > current['open'] and \
             next1['close'] < next1['open'] and next2['close'] < next2['open'] and \
             next2['close'] < current['low']:
            bearish_obs.append({
                'timestamp': current['timestamp'],
                'type': 'bearish',
                'price': current['low']
            })

    return pd.DataFrame(bullish_obs + bearish_obs)
