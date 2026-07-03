# batch_fetch.py
"""Refresh the CSVs (and models) for all supported pairs.

No config rewriting — the symbol is passed straight into the engine.
Alpha Vantage's free tier allows ~5 requests/minute, hence the pause.
"""
import time

from engine.data import get_data
from engine.model_trainer import train_and_predict
from utils.config import INTERVAL
from utils.logger import get_logger
from utils.settings import get_supported_pairs

log = get_logger("batch_fetch")

PAUSE_SECONDS = 15


def refresh_all(pairs=None, train: bool = True):
    pairs = pairs or get_supported_pairs()
    for symbol in pairs:
        log.info("=== Refreshing %s ===", symbol)
        try:
            df, source = get_data(symbol, INTERVAL, fetch=True)
            log.info("%s: %d candles (%s)", symbol, len(df), source)
            if train:
                train_and_predict(symbol, df, INTERVAL)
        except Exception as exc:
            log.error("Refresh failed for %s: %s", symbol, exc)
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    refresh_all()
