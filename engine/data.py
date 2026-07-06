# engine/data.py
"""Market data acquisition.

One entry point per symbol: get_data(symbol) fetches the freshest OHLC
series from the provider, persists it as the pair's CSV, and falls back
to the cached CSV whenever the provider is unavailable (rate limit,
network, missing API key). No global state and no config rewriting —
the symbol is a parameter.

Providers (DATA_PROVIDER env: auto | oanda | alphavantage):
  - OANDA v20 (preferred): real broker mid-price candles, up to 5000 per
    request, generous rate limits; needs OANDA_API_KEY (a free practice
    account token works). Timestamps arrive in UTC and are normalised to
    DATA_TZ (New York — the ICT kill-zone clock) so all data sources and
    the existing CSV cache share one clock.
  - Alpha Vantage (fallback): already ships US/Eastern timestamps.
  - Cached CSV (last resort): whatever was fetched previously.
"""
import glob
import os
import sys
import time

import pandas as pd
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.config import (
    ALPHA_VANTAGE_API_KEY,
    DATA_PROVIDER,
    DATA_TZ,
    FETCH_COOLDOWN_MINUTES,
    INTERVAL,
    OANDA_API_KEY,
    OANDA_ENV,
)
from utils.logger import get_logger

log = get_logger("engine.data")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 30

OANDA_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}
OANDA_GRANULARITY = {
    "1min": "M1",
    "5min": "M5",
    "15min": "M15",
    "30min": "M30",
    "60min": "H1",
    "240min": "H4",
    "daily": "D",
    "day": "D",
}

# LTF -> HTF mapping for bias context
HTF_INTERVAL_MAP = {
    "1min": "15min",
    "5min": "60min",
    "15min": "60min",
    "30min": "60min",
    "60min": "240min",
    "240min": "daily",
    "daily": "daily",
    "day": "daily",
}


def htf_interval(interval: str) -> str | None:
    """Return the higher timeframe for bias context, or None."""
    key = validate_interval(interval) if interval else INTERVAL
    return HTF_INTERVAL_MAP.get(key)
OANDA_CANDLE_COUNT = 2000  # engine analyses 1500 bars + label horizon

COLUMN_MAP = {
    "1. open": "Open",
    "2. high": "High",
    "3. low": "Low",
    "4. close": "Close",
    "5. volume": "Volume",
}


class DataUnavailableError(Exception):
    """Raised when neither the provider nor the local cache has data."""


def csv_path(symbol: str, interval: str = INTERVAL) -> str:
    return os.path.join(DATA_DIR, f"{symbol.upper()}_{interval}.csv")


def supported_intervals() -> list[str]:
    return list(OANDA_GRANULARITY.keys())


def validate_interval(interval: str) -> str:
    """Return normalised interval or raise ValueError."""
    key = (interval or "").strip().lower()
    if key not in OANDA_GRANULARITY:
        raise ValueError(
            f"Invalid interval {interval!r} (supported: {', '.join(supported_intervals())})"
        )
    return key


def normalize_symbol(symbol: str) -> str:
    """Validate and normalise a pair like 'eur/usd' or 'EUR_USD' -> 'EURUSD'."""
    symbol = (symbol or "").strip().upper().replace("/", "").replace("_", "")
    if len(symbol) != 6 or not symbol.isalpha():
        raise ValueError(f"Invalid currency pair: {symbol!r} (expected e.g. EURUSD)")
    return symbol


def to_oanda_instrument(symbol: str) -> str:
    """EURUSD -> EUR_USD for OANDA API."""
    s = normalize_symbol(symbol)
    return f"{s[:3]}_{s[3:]}"


def to_display_pair(symbol: str) -> str:
    """EURUSD -> EUR/USD for UI."""
    s = normalize_symbol(symbol)
    return f"{s[:3]}/{s[3:]}"


def from_oanda_instrument(instrument: str) -> str:
    """EUR_USD -> EURUSD."""
    return normalize_symbol(instrument)


def _frame_from_series(series: dict) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(series, orient="index")
    df = df.rename(columns=COLUMN_MAP)
    if "Volume" not in df.columns:  # FX endpoints carry no volume
        df["Volume"] = 0.0
    df.index = pd.to_datetime(df.index)
    df.index.name = "Timestamp"
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df.sort_index()


def _frame_from_oanda(candles: list[dict]) -> pd.DataFrame:
    """OANDA candles -> OHLC frame on the DATA_TZ clock.

    Only completed candles are kept — the still-forming one has no real
    close and would poison close-confirmed structure detection.
    """
    rows, times = [], []
    for c in candles:
        if not c.get("complete", False):
            continue
        mid = c["mid"]
        rows.append({
            "Open": float(mid["o"]),
            "High": float(mid["h"]),
            "Low": float(mid["l"]),
            "Close": float(mid["c"]),
            "Volume": float(c.get("volume", 0)),
        })
        times.append(c["time"])
    if not rows:
        return pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=pd.DatetimeIndex([], name="Timestamp"),
        )
    idx = (
        pd.to_datetime(times, utc=True)
        .tz_convert(DATA_TZ)
        .tz_localize(None)  # naive, same convention as the CSV cache
    )
    df = pd.DataFrame(rows, index=pd.Index(idx, name="Timestamp"))
    return df.sort_index()


def _fetch_oanda(symbol: str, interval: str) -> pd.DataFrame:
    granularity = OANDA_GRANULARITY.get(interval)
    if not granularity:
        raise LookupError(
            f"OANDA has no granularity for interval {interval!r} "
            f"(supported: {', '.join(OANDA_GRANULARITY)})"
        )
    host = OANDA_HOSTS.get(OANDA_ENV, OANDA_HOSTS["practice"])
    instrument = to_oanda_instrument(symbol)
    resp = requests.get(
        f"{host}/v3/instruments/{instrument}/candles",
        params={"granularity": granularity, "count": OANDA_CANDLE_COUNT, "price": "M"},
        headers={"Authorization": f"Bearer {OANDA_API_KEY}"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise LookupError(f"OANDA HTTP {resp.status_code}: {resp.text[:200]}")
    return _frame_from_oanda(resp.json().get("candles", []))


def _fetch_fx_intraday(symbol: str, interval: str) -> pd.DataFrame:
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": symbol[:3],
        "to_symbol": symbol[3:],
        "interval": interval,
        "outputsize": "full",
        "apikey": ALPHA_VANTAGE_API_KEY,
    }
    resp = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    key = f"Time Series FX ({interval})"
    if key not in payload:
        raise LookupError(payload.get("Note") or payload.get("Error Message") or str(list(payload.keys())))
    return _frame_from_series(payload[key])


def _fetch_ts_intraday(symbol: str, interval: str) -> pd.DataFrame:
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "outputsize": "full",
        "apikey": ALPHA_VANTAGE_API_KEY,
    }
    resp = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    key = f"Time Series ({interval})"
    if key not in payload:
        raise LookupError(payload.get("Note") or payload.get("Error Message") or str(list(payload.keys())))
    return _frame_from_series(payload[key])


def load_cached(symbol: str, interval: str = INTERVAL) -> pd.DataFrame | None:
    """Load the most recent cached CSV for a pair, searching known layouts."""
    symbol = normalize_symbol(symbol)
    candidates = [
        csv_path(symbol, interval),
        os.path.join(DATA_DIR, "1H_DATA_MAJOR_CURRENCIES", f"{symbol}_{interval}.csv"),
    ]
    candidates += sorted(
        glob.glob(os.path.join(DATA_DIR, f"{symbol}_*.csv")),
        key=os.path.getmtime,
        reverse=True,
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                df = load_ohlc_csv(path)
                if not df.empty:
                    log.info("Loaded cached data for %s from %s (%d candles)", symbol, path, len(df))
                    return df
            except Exception as exc:
                log.warning("Cached file %s unreadable: %s", path, exc)
    return None


def load_ohlc_csv(path: str) -> pd.DataFrame:
    """Read a CSV in any of the historical formats used by this project."""
    df = pd.read_csv(path)
    df = df.rename(columns={"Unnamed: 0": "Timestamp", **COLUMN_MAP})
    if "Timestamp" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Timestamp"})
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.set_index("Timestamp").sort_index()
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])
    return df


def _provider_chain() -> list[tuple[str, callable]]:
    """(label, fetcher) pairs to try, in order, per DATA_PROVIDER config."""
    chain: list[tuple[str, callable]] = []
    if DATA_PROVIDER in ("auto", "oanda") and OANDA_API_KEY:
        chain.append(("oanda", _fetch_oanda))
    if DATA_PROVIDER in ("auto", "alphavantage") and ALPHA_VANTAGE_API_KEY:
        chain.append(("alphavantage", _fetch_fx_intraday))
        chain.append(("alphavantage", _fetch_ts_intraday))
    return chain


def active_provider() -> str:
    """The provider that will serve the next live fetch ('none' if unset)."""
    chain = _provider_chain()
    return chain[0][0] if chain else "none"


def get_data(symbol: str, interval: str = INTERVAL, fetch: bool = True) -> tuple[pd.DataFrame, str]:
    """Return (ohlc_frame, source) for a pair.

    source is the provider name ('oanda' / 'alphavantage') when freshly
    fetched, 'cache' when served from disk. Fetch failures fall back to
    the next provider, then cache, so a rate-limited provider never
    takes the product down.
    """
    symbol = normalize_symbol(symbol)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Cooldown: a CSV refreshed moments ago is as good as live and the
    # provider quota (free tier: ~25 requests/day) is precious.
    if fetch and FETCH_COOLDOWN_MINUTES > 0:
        path = csv_path(symbol, interval)
        if os.path.exists(path):
            age_min = (time.time() - os.path.getmtime(path)) / 60
            if age_min < FETCH_COOLDOWN_MINUTES:
                log.info(
                    "%s CSV is %.1f min old (< %d min cooldown) — serving cache",
                    symbol, age_min, FETCH_COOLDOWN_MINUTES,
                )
                fetch = False

    if fetch:
        chain = _provider_chain()
        if not chain:
            log.warning(
                "No data provider configured (set OANDA_API_KEY or "
                "ALPHA_VANTAGE_API_KEY) — using cached data for %s", symbol,
            )
        for provider, fetcher in chain:
            try:
                df = fetcher(symbol, interval)
                if len(df) < 50:
                    raise LookupError(f"provider returned only {len(df)} candles")
                df.to_csv(csv_path(symbol, interval))
                log.info(
                    "Fetched %d candles for %s @ %s via %s",
                    len(df), symbol, interval, provider,
                )
                return df, provider
            except Exception as exc:
                log.warning("%s (%s) failed for %s: %s", provider, fetcher.__name__, symbol, exc)
                try:
                    from services.health_monitor import record_failure
                    record_failure("fetch", f"{symbol}: {exc}")
                except Exception:
                    pass

    cached = load_cached(symbol, interval)
    if cached is not None:
        try:
            from services.health_monitor import record_success
            record_success("fetch")
        except Exception:
            pass
        return cached, "cache"

    try:
        from services.health_monitor import record_failure
        record_failure("fetch", f"{symbol}: no cache")
    except Exception:
        pass

    raise DataUnavailableError(
        f"No live data and no cached CSV for {symbol} @ {interval}. "
        f"Set OANDA_API_KEY (preferred) or ALPHA_VANTAGE_API_KEY, "
        f"or place a CSV at {csv_path(symbol, interval)}."
    )


def get_latest_price(symbol: str, interval: str = INTERVAL, refresh: bool = False) -> float | None:
    """Last close for a pair — from cache by default, live when refresh=True."""
    try:
        df, _ = get_data(symbol, interval, fetch=refresh)
        return float(df["Close"].iloc[-1])
    except (DataUnavailableError, ValueError) as exc:
        log.warning("No price available for %s: %s", symbol, exc)
        return None
