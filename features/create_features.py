import os
import sys
import pandas as pd  # type: ignore

# Make sure relative imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# === Imports from modules ===
from utils.preprocess_data import preprocess_data
from smc_indicators.trend_detector import detect_trend
from smc_indicators.support_resistance import find_support_resistance
from smc_indicators.market_structure import detect_swings, label_market_structure, identify_market_trend_from_labels
from smc_indicators.bos_detector import detect_bos
from smc_indicators.fvg_detector import detect_fvg
from smc_indicators.order_blocks import detect_order_blocks
from smc_indicators.liquidity_pools import detect_liquidity_pools_with_time


# 🔁 Combine SMC & SMA trends
def combine_trends(sma, smc):
    if sma == 'Uptrend' and smc == 'Uptrend':
        return 'Strong Uptrend'
    elif sma == 'Downtrend' and smc == 'Downtrend':
        return 'Strong Downtrend'
    elif (sma == 'Uptrend' and smc == 'Sideways') or (sma == 'Sideways' and smc == 'Uptrend'):
        return 'Weak Uptrend'
    elif (sma == 'Downtrend' and smc == 'Sideways') or (sma == 'Sideways' and smc == 'Downtrend'):
        return 'Weak Downtrend'
    elif sma == 'Sideways' and smc == 'Sideways':
        return 'Sideways'
    else:
        return 'Conflict'


def extract_features(csv_path):
    df = preprocess_data(csv_path)

    # Step 1: Detect trend using SMA
    sma_trend = detect_trend(df)

    # Step 2: Support/Resistance
    support_levels, resistance_levels = find_support_resistance(df)

    # Step 3: Market structure swings + SMC trend
    swings = detect_swings(df)
    labeled_swings = label_market_structure(swings)
    smc_trend = identify_market_trend_from_labels(labeled_swings)

    labeled_swings_df = pd.DataFrame(labeled_swings)
    if 'index' not in labeled_swings_df.columns:
        labeled_swings_df['index'] = labeled_swings_df.index

    if 'timestamp' not in labeled_swings_df.columns:
        labeled_swings_df['timestamp'] = labeled_swings_df['index']

    df.reset_index(drop=False, inplace=True)

    # Step 4: BOS, FVG, OB, Liquidity Pools
    bos = detect_bos(labeled_swings_df, df)
    fvg_df = detect_fvg(df)
    ob_df = detect_order_blocks(df)
    liquidity_df = detect_liquidity_pools_with_time(labeled_swings_df)

    # === Combine trend signals ===
    combined_trend = combine_trends(sma_trend, smc_trend)

    # === Feature Summary ===
    summary = {
        "sma_trend": sma_trend,
        "smc_trend": smc_trend,
        "combined_trend": combined_trend,
        "num_support_levels": len(support_levels),
        "num_resistance_levels": len(resistance_levels),
        "num_bos_events": len(bos),
        "num_fvg": len(fvg_df),
        "num_order_blocks": len(ob_df),
        "num_liquidity_pools": len(liquidity_df),
    }

    return pd.DataFrame([summary])  # One row per file


def batch_extract_features(input_dir="data", output_dir="data/processed_features"):
    os.makedirs(output_dir, exist_ok=True)
    summary_list = []

    for file in os.listdir(input_dir):
        if file.endswith(".csv"):
            file_path = os.path.join(input_dir, file)
            print(f"🛠️ Extracting features from: {file}")
            try:
                features = extract_features(file_path)
                features["file"] = file
                summary_list.append(features)
            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

    if summary_list:
        final_df = pd.concat(summary_list, ignore_index=True)
        output_path = os.path.join(output_dir, "all_features.csv")
        final_df.to_csv(output_path, index=False)
        print(f"\n✅ Feature extraction complete. Saved to: {output_path}")
    else:
        print("⚠️ No features extracted.")


if __name__ == "__main__":
    batch_extract_features()
