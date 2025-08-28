import pandas as pd # type: ignore

def detect_liquidity_pools_with_time(swings_df, threshold=0.0005, min_points=3):
    """
    Detect liquidity pools as clusters of swing highs or lows within a price threshold,
    including the timestamps of the points in each cluster.

    :param swings_df: DataFrame with columns 'type', 'price', 'timestamp'
    :param threshold: max price range for clustering
    :param min_points: minimum points to qualify as liquidity pool
    :return: DataFrame with liquidity pool info and timestamps list
    """
    liquidity_pools = []

    # Separate highs and lows
    highs = swings_df[swings_df['type'] == 'high'].copy()
    lows = swings_df[swings_df['type'] == 'low'].copy()

    # Sort by price descending for highs (liquidity above)
    highs.sort_values('price', ascending=False, inplace=True)
    # Sort by price ascending for lows (liquidity below)
    lows.sort_values('price', ascending=True, inplace=True)

    def find_clusters(df):
        clusters = []
        cluster = []

        for _, row in df.iterrows():
            if not cluster:
                cluster = [row]
            else:
                # Check if current price close enough to last cluster point
                if abs(row['price'] - cluster[-1]['price']) <= threshold:
                    cluster.append(row)
                else:
                    if len(cluster) >= min_points:
                        clusters.append(cluster)
                    cluster = [row]

        # Check last cluster
        if len(cluster) >= min_points:
            clusters.append(cluster)
        return clusters

    high_clusters = find_clusters(highs)
    low_clusters = find_clusters(lows)

    def format_cluster(cluster, pool_type):
        prices = [row['price'] for row in cluster]
        timestamps = [row['timestamp'] for row in cluster]
        return {
            'type': pool_type,
            'price_min': min(prices),
            'price_max': max(prices),
            'points': len(cluster),
            'timestamps': timestamps,
            'time_start': min(timestamps),
            'time_end': max(timestamps)
        }

    liquidity_pools.extend([format_cluster(c, 'liquidity_above') for c in high_clusters])
    liquidity_pools.extend([format_cluster(c, 'liquidity_below') for c in low_clusters])

    return pd.DataFrame(liquidity_pools)