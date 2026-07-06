# engine/trading_style.py
"""Trading style → multi-timeframe ladder for top-down SMC/ICT analysis."""
from __future__ import annotations

STYLE_LADDERS: dict[str, dict[str, list[str]]] = {
    "scalping": {
        "parent": ["60min", "240min"],
        "structure": ["60min"],
        "setup": ["15min"],
        "execution": ["5min", "3min", "1min"],
    },
    "intraday": {
        "parent": ["240min", "60min"],
        "structure": ["60min"],
        "setup": ["30min", "15min"],
        "execution": ["5min"],
    },
    "swing": {
        "parent": ["daily", "240min"],
        "structure": ["60min"],
        "setup": ["60min"],
        "execution": ["30min", "15min"],
    },
}

VALID_STYLES = frozenset(STYLE_LADDERS.keys())

# Human-readable labels for API / UI
TF_LABELS = {
    "daily": "Daily",
    "240min": "4H",
    "60min": "1H",
    "30min": "30M",
    "15min": "15M",
    "5min": "5M",
    "3min": "3M",
    "1min": "1M",
}

HORIZON_ALIASES = {
    "scalp": "scalping",
    "scalping": "scalping",
    "intraday": "intraday",
    "day": "intraday",
    "swing": "swing",
}


def normalize_trading_style(raw: str | None) -> str:
    """Map horizon/tradingStyle input to scalping | intraday | swing."""
    key = (raw or "intraday").strip().lower().replace("-", "_")
    key = HORIZON_ALIASES.get(key, key)
    if key not in VALID_STYLES:
        return "intraday"
    return key


def ladder_for(style: str) -> dict[str, list[str]]:
    return STYLE_LADDERS[normalize_trading_style(style)]


def all_timeframes(style: str) -> list[str]:
    """Unique ordered timeframes used for a style (deduped)."""
    lad = ladder_for(style)
    seen: set[str] = set()
    out: list[str] = []
    for layer in ("parent", "structure", "setup", "execution"):
        for tf in lad.get(layer, []):
            if tf not in seen:
                seen.add(tf)
                out.append(tf)
    return out


def timeframe_labels(style: str) -> list[str]:
    return [TF_LABELS.get(tf, tf) for tf in all_timeframes(style)]


def primary_entry_tf(style: str) -> str:
    """Default entry/analysis frame when MTF auto is selected."""
    lad = ladder_for(style)
    setup = lad.get("setup") or ["30min"]
    return setup[0]


def primary_execution_tf(style: str) -> str:
    lad = ladder_for(style)
    execution = lad.get("execution") or ["5min"]
    return execution[0]
