# def find_support_resistance(df, window=5):
#     """
#     Identify support and resistance levels in the price data.
    
#     Parameters:
#     - df: pandas DataFrame with 'Low' and 'High' columns, indexed by datetime.
#     - window: number of periods on each side to consider for local min/max.
    
#     Returns:
#     - support_levels: list of tuples (timestamp, low_price) where support occurs.
#     - resistance_levels: list of tuples (timestamp, high_price) where resistance occurs.
#     """

#     support_levels = []
#     resistance_levels = []

#     for i in range(window, len(df) - window):
#         current_low = df['Low'][i]
#         current_high = df['High'][i]
#         current_time = df.index[i]

#         # Support check: current low less than neighbors
#         is_support = all(current_low < df['Low'][i - j] and current_low < df['Low'][i + j]
#                          for j in range(1, window + 1))
#         if is_support:
#             support_levels.append((current_time, current_low))

#         # Resistance check: current high greater than neighbors
#         is_resistance = all(current_high > df['High'][i - j] and current_high > df['High'][i + j]
#                             for j in range(1, window + 1))
#         if is_resistance:
#             resistance_levels.append((current_time, current_high))

#     return support_levels, resistance_levels


def find_support_resistance(df, window=5):
    support_levels = []
    resistance_levels = []

    # Use .iloc for positional access and .index for timestamps
    for i in range(window, len(df) - window):
        current_low = df['Low'].iloc[i]
        current_high = df['High'].iloc[i]
        current_time = df.index[i]  # get timestamp from index

        # Check support: current low less than lows in the window before and after
        is_support = all(
            current_low < df['Low'].iloc[i - j] and current_low < df['Low'].iloc[i + j]
            for j in range(1, window + 1)
        )
        if is_support:
            support_levels.append((current_time, current_low))

        # Check resistance: current high greater than highs in the window before and after
        is_resistance = all(
            current_high > df['High'].iloc[i - j] and current_high > df['High'].iloc[i + j]
            for j in range(1, window + 1)
        )
        if is_resistance:
            resistance_levels.append((current_time, current_high))

    return support_levels, resistance_levels
