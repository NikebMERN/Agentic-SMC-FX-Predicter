"""OANDA pricing stream relay for live charts."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict

import requests

from utils.config import OANDA_API_KEY, OANDA_ENV
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
    sym = pair.upper()
    with _lock:
        _subscribers[sym].add(callback)
        if sym not in _stream_threads or not _stream_threads[sym].is_alive():
            t = threading.Thread(target=_stream_loop, args=(sym,), daemon=True, name=f"oanda-{sym}")
            _stream_threads[sym] = t
            t.start()


def unsubscribe(pair: str, callback) -> None:
    sym = pair.upper()
    with _lock:
        _subscribers[sym].discard(callback)


def _broadcast(sym: str, tick: dict):
    with _lock:
        _latest[sym] = tick
        subs = list(_subscribers.get(sym, []))
    for cb in subs:
        try:
            cb(tick)
        except Exception:
            pass


def _stream_loop(sym: str):
    if not OANDA_API_KEY:
        # Mock ticks for dev without OANDA
        price = 1.1000
        while True:
            price += 0.00005
            tick = {"pair": sym, "bid": price - 0.0001, "ask": price + 0.0001, "mid": price, "time": time.time()}
            _broadcast(sym, tick)
            time.sleep(1)
        return

    instrument = _instrument(sym)
    url = f"{OANDA_STREAM_BASE}/v3/accounts/{os.getenv('OANDA_ACCOUNT_ID', '')}/pricing/stream"
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    params = {"instruments": instrument}

    while True:
        try:
            with requests.get(url, headers=headers, params=params, stream=True, timeout=60) as resp:
                for line in resp.iter_lines():
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
            log.warning("OANDA stream error for %s: %s — retrying", sym, exc)
            time.sleep(5)
