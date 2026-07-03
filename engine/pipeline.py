# engine/pipeline.py
"""The one prediction flow.

predict_symbol("EURUSD") does, in order:
  1. Pull the latest CSV for that pair (live fetch, cache fallback).
  2. Detect every VALID SMC + ICT signal on that data.
  3. Train the pair's model on that same data, fresh.
  4. Aggregate both strategies + the model into one decision
     (BUY / SELL / NO_TRADE with entry, SL, TP and reasoning).

on_progress(stage, message) lets callers (SSE endpoint, Telegram bot,
CLI) stream status while the pipeline runs.
"""
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import confluence
from engine.data import get_data, normalize_symbol, htf_interval
from engine.model_trainer import train_and_predict
from engine.signals_export import export_signals
from utils.config import INTERVAL
from utils.logger import get_logger

log = get_logger("engine.pipeline")

ProgressFn = Callable[[str, str], None]

# Training is CPU-heavy; concurrent requests for the SAME pair would
# redo identical work and contend for cores. One at a time per symbol —
# different pairs still run in parallel.
_symbol_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(symbol: str) -> threading.Lock:
    with _locks_guard:
        return _symbol_locks[symbol]


def _compute_htf_bias(symbol: str, interval: str, fetch: bool) -> dict | None:
    """Fetch higher timeframe and derive structure bias."""
    htf_iv = htf_interval(interval)
    if not htf_iv:
        return None
    try:
        df_htf, _ = get_data(symbol, htf_iv, fetch=fetch)
        if df_htf.empty:
            return None
        htf_analysis = confluence.analyze(df_htf, symbol)
        events = htf_analysis["structure"]["events"]
        if not events:
            return {
                "direction": "neutral",
                "strength": 0,
                "confidence": 0.5,
                "interval": htf_iv,
                "reason": f"No HTF structure on {htf_iv}",
            }
        ev = events[-1]
        return {
            "direction": ev["direction"],
            "strength": 80 if ev.get("displacement") else 60,
            "confidence": 0.75 if ev.get("displacement") else 0.6,
            "interval": htf_iv,
            "reason": f"HTF {ev['kind']} {ev['direction']} on {htf_iv}",
            "trend": htf_analysis["structure"]["trend"],
        }
    except Exception as exc:
        log.debug("HTF bias unavailable for %s/%s: %s", symbol, interval, exc)
        return None


def predict_symbol(
    symbol: str,
    interval: str | None = None,
    fetch: bool = True,
    strategy_mode: str = "both",
    on_progress: ProgressFn | None = None,
) -> dict:
    """Full fetch -> analyze -> train -> decide cycle for one pair."""
    symbol = normalize_symbol(symbol)
    interval = interval or INTERVAL
    from engine.confluence import normalize_strategy_mode
    strategy_mode = normalize_strategy_mode(strategy_mode)
    with _lock_for(f"{symbol}_{interval}"):
        return _predict_locked(symbol, interval, fetch, strategy_mode, on_progress)


def _predict_locked(
    symbol: str,
    interval: str,
    fetch: bool,
    strategy_mode: str,
    on_progress: ProgressFn | None,
) -> dict:

    def progress(stage: str, message: str):
        log.info("[%s] %s: %s", symbol, stage, message)
        if on_progress:
            on_progress(stage, message)

    progress("fetch", f"Pulling latest {interval} data for {symbol}...")
    df, source = get_data(symbol, interval, fetch=fetch)
    progress("data", f"{len(df)} candles loaded (source: {source}, last candle: {df.index[-1]})")

    progress("analyze", f"Detecting valid signals ({strategy_mode}: SMC/ICT) on {symbol}...")
    analysis = confluence.analyze(df, symbol)
    htf_bias = _compute_htf_bias(symbol, interval, fetch)
    if htf_bias:
        analysis["htf_bias"] = htf_bias
        progress("analyze", f"HTF bias: {htf_bias['direction']} ({htf_bias['interval']})")

    progress("train", "Training the model on this pair's latest data...")
    ml_signal = None
    try:
        ml_signal = train_and_predict(symbol, df, interval)
        if ml_signal:
            progress(
                "train",
                f"Model trained ({ml_signal['metrics']['samples']} samples, "
                f"validation accuracy {ml_signal['metrics']['val_accuracy']:.1%})",
            )
        else:
            progress("train", "Not enough data for an honest model - using rule confluence only")
    except Exception as exc:
        log.exception("ML training failed for %s", symbol)
        progress("train", f"Model training failed ({exc}) - using rule confluence only")

    progress("decide", f"Aggregating confluence ({strategy_mode}) into a decision...")
    decision = confluence.decide(analysis, ml_signal, strategy_mode=strategy_mode)
    structured_signals = export_signals(analysis, interval=interval)

    from engine.features import build_features
    feat_df = build_features(df)
    last_feats = feat_df.iloc[-1]
    feature_snapshot = {
        col: (None if pd.isna(val) else float(val))
        for col, val in last_feats.items()
    }

    candle_snapshot = []
    for ts, row in df.tail(50).iterrows():
        candle_snapshot.append({
            "time": str(ts),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0)),
        })

    result = {
        "symbol": symbol,
        "interval": interval,
        "strategy": strategy_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": source,
        "last_candle": str(analysis["last_time"]),
        "candles": analysis["bars"],
        "decision": decision,
        "structured_signals": structured_signals,
        "candle_snapshot": candle_snapshot,
        "feature_snapshot": feature_snapshot,
        "ml": ml_signal["metrics"] if ml_signal else None,
        "analysis_summary": {
            "structure_events": len(analysis["structure"]["events"]),
            "trend": analysis["structure"]["trend"],
            "valid_order_blocks": len(analysis["valid_order_blocks"]),
            "valid_fvgs": len(analysis["fvgs"]),
            "liquidity_pools": len(analysis["pools"]),
            "recent_sweeps": len(analysis["sweeps"]),
            "breakers": len(analysis["breakers"]),
            "killzone": analysis["killzone"],
            "dealing_range": analysis["dealing_range"],
            "premium_discount": analysis["premium_discount"],
            "htf_bias": analysis.get("htf_bias"),
        },
    }
    progress("done", f"{symbol}: {decision['action']} (confidence {decision['confidence']:.0%})")
    return result


def format_result_text(result: dict, markdown: bool = False) -> str:
    """Human-readable rendering shared by the CLI and the Telegram bot."""
    d = result["decision"]
    b = "*" if markdown else ""
    lines = [
        f"{b}{result['symbol']} - {d['action']}{b}",
        f"Strategy: {d.get('strategy', result.get('strategy', 'both'))}",
        f"Confidence: {d['confidence']:.0%} (rules {d['rule_confidence']:.0%}"
        + (f", ML {d['ml_confidence']:.0%})" if d.get("ml_confidence") is not None else ")"),
        f"Scores: bullish {d['scores']['bullish']} vs bearish {d['scores']['bearish']} "
        f"({d['confluences']} valid confluences)",
    ]
    if confluence.is_trade_action(d["action"]):
        sl_extra = (
            f" ({d['sl_pips']} pips / {d['sl_pct']}%)"
            if d.get("sl_pips") is not None else ""
        )
        tp_extra = (
            f" ({d['tp_pips']} pips / {d['tp_pct']}%)"
            if d.get("tp_pips") is not None else ""
        )
        lines += [
            f"Entry: {d['entry']}",
            f"Stop Loss: {d.get('invalidation_price') or d.get('stop_loss')}{sl_extra}",
            f"Take Profit: {d.get('target_liquidity') or d.get('take_profit')}{tp_extra}",
            f"Risk/Reward: {d['risk_reward']}",
        ]
    elif d["action"] == confluence.ACTION_WAIT:
        lines.append("Setup forming — wait for confirmation before acting.")
        if d.get("invalidation_price"):
            lines.append(f"Watch invalidation: {d['invalidation_price']}")
    if d.get("killzone"):
        lines.append(f"Kill zone: {d['killzone']}")
    lines.append("")
    lines.append(f"{b}Why:{b}")
    lines += [f"- {r}" for r in d["reasoning"]]
    if d["vetoes"]:
        lines.append(f"{b}Vetoes:{b}")
        lines += [f"- {v}" for v in d["vetoes"]]
    if result.get("ml"):
        lines.append(
            f"Model: {result['ml']['samples']} samples, "
            f"val accuracy {result['ml']['val_accuracy']:.1%}"
        )
    lines.append(
        f"Data: {result['candles']} candles ({result['data_source']}), last {result['last_candle']}"
    )
    lines.append(d.get("disclaimer", "Not financial advice."))
    return "\n".join(lines)
