# main.py
"""Terminal prediction client.

    python main.py             -> interactive pair menu
    python main.py EURUSD      -> predict one pair directly
    python main.py EURUSD --no-fetch  -> use the cached CSV (no API call)

Each run pulls the pair's latest CSV, retrains its model on that data,
then prints the aggregated valid-SMC/ICT decision.
"""
import argparse
import sys

from engine.pipeline import predict_symbol, format_result_text
from utils.settings import get_supported_pairs


def choose_pair() -> str:
    pairs = get_supported_pairs()
    print("Available currency pairs:\n")
    for idx, pair in enumerate(pairs, start=1):
        print(f"  {idx}. {pair}")
    raw = input("\nEnter a number or type any pair (e.g. EURUSD): ").strip()
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(pairs):
            return pairs[idx - 1]
        print("Invalid choice.")
        sys.exit(1)
    return raw


def main():
    parser = argparse.ArgumentParser(description="SMC/ICT forex predictor")
    parser.add_argument("symbol", nargs="?", help="currency pair, e.g. EURUSD")
    parser.add_argument("--interval", default=None, help="candle interval (default from env)")
    parser.add_argument("--no-fetch", action="store_true", help="use cached CSV, skip the live fetch")
    args = parser.parse_args()

    symbol = args.symbol or choose_pair()

    def on_progress(stage, message):
        print(f"[{stage.upper()}] {message}")

    result = predict_symbol(
        symbol,
        interval=args.interval,
        fetch=not args.no_fetch,
        on_progress=on_progress,
    )
    print("\n" + "=" * 60)
    print(format_result_text(result))
    print("=" * 60)


if __name__ == "__main__":
    main()
