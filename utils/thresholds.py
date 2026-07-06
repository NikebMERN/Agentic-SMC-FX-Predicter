# utils/thresholds.py
"""Backward-compatible threshold access — delegates to threshold_service."""
from __future__ import annotations

import json
from typing import Any

from config.smc_ict_thresholds import DEFAULT_THRESHOLDS as _DEFAULT_MODEL
from schemas.threshold_schema import thresholds_to_legacy_flat
from services import threshold_service
from utils.logger import get_logger

log = get_logger("utils.thresholds")

# Legacy flat defaults for tests and admin UI compatibility
DEFAULT_THRESHOLDS: dict[str, float | int] = thresholds_to_legacy_flat(_DEFAULT_MODEL)


def get_thresholds(symbol: str | None = None, interval: str = "*", trading_style: str = "intraday") -> dict:
    """Resolved flat thresholds for gradual migration."""
    sym = symbol or "EURUSD"
    tf = interval if interval != "*" else "60min"
    thresholds, _ = threshold_service.resolve_thresholds(sym, tf, trading_style)
    return thresholds_to_legacy_flat(thresholds, tf, trading_style)


def get_thresholds_model(symbol: str | None = None, interval: str = "60min", trading_style: str = "intraday"):
    return threshold_service.resolve_thresholds_model(symbol or "EURUSD", interval, trading_style)


def invalidate_cache():
    threshold_service.invalidate_cache()


def save_global_thresholds(updates: dict) -> dict:
    """Legacy: patch active version from flat keys."""
    patch = threshold_service._flat_to_nested_patch(updates)
    threshold_service.patch_active_version(patch)
    return get_thresholds()


def save_pair_thresholds(symbol: str, interval: str, updates: dict) -> dict:
    sym = symbol.upper()
    iv = interval or "*"
    patch = threshold_service._flat_to_nested_patch(updates)
    threshold_service.save_override(sym, iv, "*", patch)
    return get_thresholds(sym, iv)


def list_pair_thresholds() -> list[dict]:
    return threshold_service.list_overrides()
