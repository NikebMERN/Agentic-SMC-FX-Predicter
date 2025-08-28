import pandas as pd

def detect_trend(df, short_window=10, long_window=50):
    """
    Detect trend using SMA crossover on a DataFrame.
    
    Parameters:
        df (pd.DataFrame): DataFrame with at least 'Close' column.
        short_window (int): Window size for short SMA.
        long_window (int): Window size for long SMA.
    
    Returns:
        str: 'Uptrend', 'Downtrend', or 'No clear trend'
    """
    # Make sure Close column is float
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    
    # Calculate SMAs
    df['SMA_short'] = df['Close'].rolling(window=short_window).mean()
    df['SMA_long'] = df['Close'].rolling(window=long_window).mean()

    # Check last available values
    if pd.isna(df['SMA_short'].iloc[-1]) or pd.isna(df['SMA_long'].iloc[-1]):
        return "No data"

    # Determine trend by SMA crossover
    if df['SMA_short'].iloc[-1] > df['SMA_long'].iloc[-1]:
        return "Uptrend"
    elif df['SMA_short'].iloc[-1] < df['SMA_long'].iloc[-1]:
        return "Downtrend"
    else:
        return "No clear trend"
