# utils/pairs.py
"""Default tradable FX pairs for menus, batch_fetch, and the web UI.

Override with SUPPORTED_PAIRS in .env or the admin Settings panel.
Env values may use EURUSD or EUR/USD format.
"""
from __future__ import annotations

import os
import re

# Full platform catalog (96 unique pairs; table rows 61–64 duplicate USD lines).
DEFAULT_FX_PAIRS: list[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "CADJPY", "CADCHF",
    "CHFJPY",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "SGDJPY", "HKDJPY",
    "USDSGD", "USDHKD", "USDCNH", "USDTHB",
    "USDKRW", "USDTWD", "USDMYR", "USDPHP",
    "USDIDR", "USDVND", "USDSAR", "USDAED",
    "USDQAR", "USDKWD", "USDBHD", "USDOMR",
    "USDEGP", "USDNGN", "USDKES", "USDETB",
    "USDZAR", "USDTRY", "USDMXN", "USDSEK", "USDNOK", "USDDKK", "USDPLN", "USDHUF", "USDCZK", "USDILS",
    "USDINR", "USDBRL",
    "EURZAR", "EURTRY", "EURMXN", "EURSEK", "EURNOK", "EURDKK", "EURPLN", "EURHUF", "EURCZK",
    "EURSGD", "EURHKD",
    "GBPZAR", "GBPTRY", "GBPMXN", "GBPSEK", "GBPNOK", "GBPDKK", "GBPPLN", "GBPHUF", "GBPCZK", "GBPSGD",
    "AUDZAR", "AUDSGD", "AUDHKD", "AUDCNH",
    "NZDSGD", "NZDHKD",
    "CADSGD", "CADHKD",
    "CHFSGD", "CHFHKD",
    "SEKJPY", "NOKJPY", "MXNJPY",
]

_CATALOG_VERSION = "2026-04-100"
_CSV_PAIR_RE = re.compile(r"^([A-Z]{6})_\d+min\.csv$", re.I)


def normalize_pair_code(raw: str) -> str:
    """EUR/USD, eurusd -> EURUSD."""
    s = (raw or "").strip().upper().replace("/", "")
    if len(s) != 6 or not s.isalpha():
        raise ValueError(f"Invalid currency pair: {raw!r}")
    return s


def pairs_from_env(raw: str | None) -> list[str] | None:
    if not raw or not raw.strip():
        return None
    out: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(normalize_pair_code(part))
    return out or None


def pairs_from_data_dir(data_dir: str, interval: str) -> list[str]:
    """Discover pairs that already have a cached CSV on disk."""
    if not os.path.isdir(data_dir):
        return []
    found: list[str] = []
    suffix = f"_{interval}.csv"
    for name in os.listdir(data_dir):
        if not name.lower().endswith(suffix.lower()):
            continue
        m = _CSV_PAIR_RE.match(name)
        if m:
            found.append(m.group(1).upper())
    return found


def merge_pairs(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for p in lst:
            key = p.upper()
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def catalog_version() -> str:
    return _CATALOG_VERSION
