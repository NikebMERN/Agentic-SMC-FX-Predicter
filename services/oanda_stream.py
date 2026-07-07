"""OANDA pricing stream relay for live charts."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict

import requests

from utils.config import (
    APP_ENV,
    MARKET_STREAMS_ENABLED,
    MAX_MARKET_STREAMS,
    OANDA_API_KEY,
    OANDA_ENV,
)
from utils.logger import get_logger

log = get_logger("services.oanda_stream")

OANDA_STREAM_BASE = (
    "https://stream-fxpractice.oanda.com"
    if OANDA_ENV != "live"
    else "https://stream-fxtrade.oanda.com"
)

_subscribers: dict[str, set] = defaultdict(set)
_latest: dict[str, dict] = {}
_lock = threading.Lock()
_stream_threads: dict[str, threading.Thread] = {}


def _instrument(pair: str) -> str:
    p = pair.upper().replace("/", "")
    if len(p) == 6:
        return f"{p[:3]}_{p[3:]}"
    return p


def get_latest_quote(pair: str) -> dict | None:
    with _lock:
        return _latest.get(pair.upper())


def subscribe(pair: str, callback) -> None:
    if not MARKET_STREAMS_ENABLED:
        raise RuntimeError("Live market streams are disabled.")
    sym = pair.upper()
    with _lock:
        _subscribers[sym].add(callback)
        if sym not in _stream_threads or not _stream_threads[sym].is_alive():
            active = [thread for thread in _stream_threads.values() if thread.is_alive()]
            if len(active) >= MAX_MARKET_STREAMS:
                _subscribers[sym].discard(callback)
                raise RuntimeError("Live market stream limit reached.")
            thread = threading.Thread(
                target=_stream_loop,
                args=(sym,),
                daemon=True,
                name=f"oanda-{sym}",
            )
            _stream_threads[sym] = thread
            thread.start()


def unsubscribe(pair: str, callback) -> None:
    sym = pair.upper()
    with _lock:
        _subscribers[sym].discard(callback)


def _broadcast(sym: str, tick: dict):
    with _lock:
        _latest[sym] = tick
        subscribers = list(_subscribers.get(sym, []))
    for callback in subscribers:
        try:
            callback(tick)
        except Exception:
            pass


def _has_subscribers(sym: str) -> bool:
    with _lock:
        return bool(_subscribers.get(sym))


def _cleanup_stream(sym: str) -> None:
    with _lock:
        if not _subscribers.get(sym):
            _subscribers.pop(sym, None)
            _stream_threads.pop(sym, None)


def _stream_loop(sym: str):
    if not OANDA_API_KEY:
        if APP_ENV == "production":
            log.warning("OANDA_API_KEY missing - live stream disabled for %s in production", sym)
            _cleanup_stream(sym)
            return
        price = 1.1000
        while _has_subscribers(sym):
            price += 0.00005
            tick = {
                "pair": sym,
                "bid": price - 0.0001,
                "ask": price + 0.0001,
                "mid": price,
                "time": time.time(),
            }
            _broadcast(sym, tick)
            time.sleep(1)
        _cleanup_stream(sym)
        return

    instrument = _instrument(sym)
    url = f"{OANDA_STREAM_BASE}/v3/accounts/{os.getenv('OANDA_ACCOUNT_ID', '')}/pricing/stream"
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    params = {"instruments": instrument}

    while _has_subscribers(sym):
        try:
            with requests.get(url, headers=headers, params=params, stream=True, timeout=60) as resp:
                for line in resp.iter_lines():
                    if not _has_subscribers(sym):
                        break
                    if not line:
                        continue
                    data = json.loads(line.decode("utf-8"))
                    if data.get("type") != "PRICE":
                        continue
                    bids = data.get("bids", [{}])
                    asks = data.get("asks", [{}])
                    bid = float(bids[0].get("price", 0))
                    ask = float(asks[0].get("price", 0))
                    tick = {
                        "pair": sym,
                        "bid": bid,
                        "ask": ask,
                        "mid": (bid + ask) / 2,
                        "time": data.get("time"),
                    }
                    _broadcast(sym, tick)
        except Exception as exc:
            log.warning("OANDA stream error for %s: %s - retrying", sym, exc)
            time.sleep(5)
    _cleanup_stream(sym)
