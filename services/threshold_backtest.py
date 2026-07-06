# services/threshold_backtest.py
"""Compare threshold versions on historical data."""
from __future__ import annotations

import json

from db.models import ThresholdVersion
from db.session import SessionLocal
from engine.backtest import run_backtest
from schemas.threshold_schema import SmcIctThresholds, validate_threshold_config
from config.smc_ict_thresholds import DEFAULT_THRESHOLDS, resolve_thresholds
from utils.logger import get_logger

log = get_logger("services.threshold_backtest")


def _load_version_config(version_id: int) -> tuple[SmcIctThresholds, ThresholdVersion]:
    db = SessionLocal()
    try:
        row = db.query(ThresholdVersion).filter(ThresholdVersion.id == version_id).first()
        if not row:
            raise ValueError(f"Threshold version {version_id} not found")
        try:
            config = json.loads(row.config_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid version config_json") from exc
        return validate_threshold_config(config), row
    finally:
        db.close()


def run_threshold_backtest(
    symbol: str,
    df,
    thresholds: SmcIctThresholds,
    *,
    trading_style: str = "intraday",
    interval: str = "60min",
) -> dict:
    return run_backtest(
        df,
        symbol,
        thresholds=thresholds,
        trading_style=trading_style,
        interval=interval,
    )


def compare_threshold_versions(
    symbol: str,
    df,
    version_a_id: int,
    version_b_id: int,
    *,
    trading_style: str = "intraday",
    interval: str = "60min",
) -> dict:
    config_a, row_a = _load_version_config(version_a_id)
    config_b, row_b = _load_version_config(version_b_id)
    resolved_a = resolve_thresholds(symbol, interval, trading_style, version_config=config_a)
    resolved_b = resolve_thresholds(symbol, interval, trading_style, version_config=config_b)
    metrics_a = run_threshold_backtest(symbol, df, resolved_a, trading_style=trading_style, interval=interval)
    metrics_b = run_threshold_backtest(symbol, df, resolved_b, trading_style=trading_style, interval=interval)
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "trading_style": trading_style,
        "version_a": {"id": row_a.id, "tag": row_a.version_tag, "metrics": metrics_a},
        "version_b": {"id": row_b.id, "tag": row_b.version_tag, "metrics": metrics_b},
        "delta": _delta(metrics_a, metrics_b),
    }


def _delta(a: dict, b: dict) -> dict:
    if a.get("error") or b.get("error"):
        return {"error": "One or both backtests failed"}
    keys = ("accuracy", "no_trade_rate", "wait_rate", "invalidation_hit_rate", "trades")
    out = {}
    for k in keys:
        av = a.get(k, 0) or 0
        bv = b.get(k, 0) or 0
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            out[k] = round(bv - av, 4)
    return out


def backtest_active_vs_defaults(symbol: str, df, **kwargs) -> dict:
    from services.threshold_service import get_active_version
    active = get_active_version()
    if not active:
        return compare_threshold_versions(
            symbol, df, 0, 0, **kwargs
        ) if False else {
            "error": "No active threshold version",
            "defaults": run_threshold_backtest(symbol, df, DEFAULT_THRESHOLDS, **kwargs),
        }
    return compare_threshold_versions(symbol, df, active.id, active.id, **kwargs)
