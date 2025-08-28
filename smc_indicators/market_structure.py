import pandas as pd

def detect_swings(df, window=3):
    """
    Detects swing highs and lows in the price data.
    
    Args:
        df (pd.DataFrame): DataFrame with 'High' and 'Low' columns and datetime index.
        window (int): Number of bars to look back and forward for swing validation.
        
    Returns:
        swings (list of dict): Each dict contains:
            - 'type': 'high' or 'low'
            - 'index': Timestamp
            - 'price': float
    """
    swings = []
    highs = df['High']
    lows = df['Low']
    
    for i in range(window, len(df) - window):
        current_high = highs.iloc[i]
        current_low = lows.iloc[i]
        
        is_swing_high = all(current_high > highs.iloc[i - j] for j in range(1, window + 1)) and \
                        all(current_high > highs.iloc[i + j] for j in range(1, window + 1))
        is_swing_low = all(current_low < lows.iloc[i - j] for j in range(1, window + 1)) and \
                       all(current_low < lows.iloc[i + j] for j in range(1, window + 1))
        
        if is_swing_high:
            swings.append({'type': 'high', 'index': df.index[i], 'price': current_high})
        if is_swing_low:
            swings.append({'type': 'low', 'index': df.index[i], 'price': current_low})
    return swings

def label_market_structure(swings):
    """
    Labels swings as HH, HL, LH, LL depending on sequence and price.
    Assumes swings are ordered by time.
    
    Args:
        swings (list of dict): output from detect_swings
    
    Returns:
        labeled_swings (list of dict): adds 'label' key with one of:
            'HH' - Higher High
            'HL' - Higher Low
            'LH' - Lower High
            'LL' - Lower Low
            or 'N/A' if undetermined
    """
    labeled_swings = []
    
    # Filter highs and lows separately to compare
    last_high = None
    last_low = None
    
    for i, current in enumerate(swings):
        if current['type'] == 'high':
            if last_high is None:
                label = 'N/A'  # no previous high to compare
            else:
                label = 'HH' if current['price'] > last_high else 'LH'
            last_high = current['price']
        else:  # low
            if last_low is None:
                label = 'N/A'  # no previous low to compare
            else:
                label = 'HL' if current['price'] > last_low else 'LL'
            last_low = current['price']
        
        labeled_swings.append({**current, 'label': label})
    
    return labeled_swings

def identify_market_trend_from_labels(labeled_swings):
    """
    Uses the last few labeled swings to guess market trend.
    
    Args:
        labeled_swings (list of dict)
    
    Returns:
        str: "Uptrend", "Downtrend", or "Sideways"
    """
    # Focus only on meaningful labels (exclude 'N/A')
    filtered = [s for s in labeled_swings if s['label'] != 'N/A']
    if len(filtered) < 4:
        return "Not enough data to determine trend"
    
    # Check the last 4 swings (2 highs and 2 lows ideally)
    last_labels = [s['label'] for s in filtered[-4:]]

    # Basic logic:
    # Uptrend: Contains HH and HL mostly
    if all(lbl in ['HH', 'HL'] for lbl in last_labels):
        return "Uptrend"
    # Downtrend: Contains LH and LL mostly
    elif all(lbl in ['LH', 'LL'] for lbl in last_labels):
        return "Downtrend"
    else:
        return "Sideways"