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
    mtf: bool | None = None,
    trading_style: str = "intraday",
) -> dict:
    """Full fetch -> analyze -> train -> decide cycle for one pair.

    Default mode is the liquidity-first multi-timeframe stack driven by
    trading_style (scalping / intraday / swing).
    Passing an explicit non-default interval (or mtf=False) runs the
    single-timeframe analysis on that interval instead.
    """
    from engine.trading_style import normalize_trading_style, primary_entry_tf

    symbol = normalize_symbol(symbol)
    from engine.confluence import normalize_strategy_mode
    strategy_mode = normalize_strategy_mode(strategy_mode)
    style = normalize_trading_style(trading_style)
    if mtf is None:
        mtf = interval in (None, "", "30min", primary_entry_tf(style))
    interval = interval or primary_entry_tf(style)
    lock_key = f"{symbol}_mtf_{style}" if mtf else f"{symbol}_{interval}"
    with _lock_for(lock_key):
        return _predict_locked(symbol, interval, fetch, strategy_mode, on_progress, mtf, style)


def _predict_locked(
    symbol: str,
    interval: str,
    fetch: bool,
    strategy_mode: str,
    on_progress: ProgressFn | None,
    mtf: bool,
    trading_style: str = "intraday",
) -> dict:

    def progress(stage: str, message: str):
        log.info("[%s] %s: %s", symbol, stage, message)
        if on_progress:
            on_progress(stage, message)

    from engine.candle_validator import validate_candles
    from engine.prediction_response import build_prediction_response
    from engine.trading_style import normalize_trading_style, timeframe_labels
    from services.threshold_service import resolve_thresholds

    style = normalize_trading_style(trading_style)
    thresholds, threshold_version_id = resolve_thresholds(symbol, interval, style)
    mtf_context = None
    validation = None
    spread_ok = True
    data_valid = True

    if mtf:
        from engine.topdown import topdown_analyze
        progress("fetch", f"Top-down analysis for {symbol} ({style}): {' -> '.join(timeframe_labels(style))}...")
        stack = topdown_analyze(symbol, fetch, trading_style=style, progress=progress)
        analysis = stack["analysis"]
        df = stack["entry_df"]
        source = stack["source"]
        interval = stack["entry_tf"]
        mtf_context = stack["context"]
        thresholds = stack.get("thresholds", thresholds)
        threshold_version_id = stack.get("threshold_version_id", threshold_version_id)
        progress("data", f"{len(df)} entry candles ({interval}, source: {source}, last: {df.index[-1]})")
    else:
        progress("fetch", f"Pulling latest {interval} data for {symbol}...")
        df, source = get_data(symbol, interval, fetch=fetch)
        progress("data", f"{len(df)} candles loaded (source: {source}, last candle: {df.index[-1]})")

        progress("analyze", f"Detecting valid signals ({strategy_mode}: SMC/ICT) on {symbol}...")
        analysis = confluence.analyze(df, symbol, interval=interval, thresholds=thresholds, trading_style=style)
        analysis["threshold_version_id"] = threshold_version_id
        htf_bias = _compute_htf_bias(symbol, interval, fetch)
        if htf_bias:
            analysis["htf_bias"] = htf_bias
            analysis["higher_timeframe_bias"] = htf_bias.get("direction", "neutral").upper()
            progress("analyze", f"HTF bias: {htf_bias['direction']} ({htf_bias['interval']})")
        analysis["trading_style"] = style

    validation = validate_candles(df, symbol, interval, thresholds=thresholds, trading_style=style)
    data_valid = validation["valid"]
    if validation["warnings"]:
        progress("data", "; ".join(validation["warnings"][:2]))
    if not data_valid:
        progress("data", f"Data validation: {'; '.join(validation['errors'][:2])}")

    # ml_mode: "active" uses promoted meta-model (default); "fresh" is deprecated.
    from utils import settings as runtime_settings
    ml_mode = (runtime_settings.get("ml_mode", "active") or "active").lower()

    progress("decide", f"Aggregating confluence ({strategy_mode}) into a decision...")
    decision = confluence.decide(
        analysis, None, strategy_mode=strategy_mode,
        spread_ok=spread_ok, data_valid=data_valid, thresholds=thresholds,
    )

    from ml.feature_schema import build_meta_features, RULE_ENGINE_VERSION
    from schemas.meta_feature_schema import FEATURE_SCHEMA_VERSION
    meta_features = build_meta_features(
        analysis, decision,
        spread_ok=spread_ok, data_valid=data_valid,
        threshold_version_id=threshold_version_id,
    )
    meta_snapshot = meta_features.model_dump()

    ml_probability = None
    model_version_id = None
    has_active_model = False
    if ml_mode == "active":
        from services.ml_service import predict_meta_quality
        ml_probability, model_version_id = predict_meta_quality(
            meta_features, symbol, interval, style,
        )
        has_active_model = model_version_id is not None
        if has_active_model and ml_probability is not None:
            progress(
                "ml_gate",
                f"Meta-model P(win)={ml_probability:.2f} (version {model_version_id})",
            )
        else:
            progress("ml_gate", "No active meta-model — rule-only with confidence cap")
    elif ml_mode == "fresh":
        progress("ml_gate", "Legacy fresh-training mode deprecated — using active meta-model path")
        from services.ml_service import predict_meta_quality
        ml_probability, model_version_id = predict_meta_quality(
            meta_features, symbol, interval, style,
        )
        has_active_model = model_version_id is not None

    from engine.ml_gate import apply_ml_gate
    decision = apply_ml_gate(
        decision,
        ml_probability=ml_probability,
        has_active_model=has_active_model,
    )
    structured_signals = export_signals(analysis, interval=interval)
    prediction = build_prediction_response(
        symbol, style, decision, analysis,
        mtf_context=mtf_context, validation=validation,
    )

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

    # Automated pip / position calculator (default account assumptions;
    # clients recalculate live via POST /calculator).
    calculator = None
    if decision.get("entry") and decision.get("stop_loss") and decision.get("take_profit"):
        try:
            from engine.risk_calc import pip_calculator
            calculator = pip_calculator(
                symbol, decision["entry"], decision["stop_loss"], decision["take_profit"],
            )
        except Exception as exc:
            log.warning("pip calculator failed for %s: %s", symbol, exc)

    result = {
        "symbol": symbol,
        "interval": interval,
        "trading_style": style,
        "strategy": strategy_mode,
        "mtf": mtf_context,
        "prediction": prediction,
        "validation": validation,
        "calculator": calculator,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": source,
        "data_diagnostics": __import__("engine.data", fromlist=["get_last_data_diagnostics"]).get_last_data_diagnostics(),
        "last_candle": str(analysis["last_time"]),
        "candles": analysis["bars"],
        "decision": decision,
        "structured_signals": structured_signals,
        "candle_snapshot": candle_snapshot,
        "feature_snapshot": feature_snapshot,
        "meta_feature_snapshot": meta_snapshot,
        "ml": {
            "mode": ml_mode,
            "meta_ml_probability": ml_probability,
            "model_version_id": model_version_id,
            "has_active_model": has_active_model,
            "rule_engine_version": RULE_ENGINE_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        },
        "threshold_version_id": threshold_version_id,
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
    ]
    calc = result.get("calculator") or {}
    summary = result.get("analysis_summary") or {}
    confirmation = d.get("institutional_confirmation") or {}
    confirmation_reasons = confirmation.get("reasons") or []
    if isinstance(confirmation_reasons, str):
        confirmation_reasons = [confirmation_reasons]
    confirmation_reason = (
        "; ".join(str(reason) for reason in confirmation_reasons)
        or next(
            (str(reason) for reason in d.get("reasoning", []) if any(
                key in str(reason).lower() for key in ("confirm", "mss", "choch")
            )),
            "Rule-based institutional confluence",
        )
    )
    direction = d.get("direction") or d.get("action") or "N/A"
    session = d.get("killzone") or summary.get("killzone") or "Outside kill zone"
    trend = d.get("market_trend") or summary.get("trend") or "N/A"
    lines += [
        f"Pair: {result['symbol']}",
        f"Direction: {direction}",
        f"Entry: {d.get('entry', 'N/A')}",
        f"Stop Loss: {d.get('stop_loss') or d.get('invalidation_price') or 'N/A'}",
        f"Take Profit: {d.get('take_profit') or d.get('target_liquidity') or 'N/A'}",
        f"Risk Reward: {d.get('risk_reward', 'N/A')}",
        f"Confidence: {d.get('confidence', 0):.0%}",
        f"Lot Size: {calc.get('lot_size', 'N/A')}",
        f"Position Size: {calc.get('position_size', 'N/A')}",
        f"Strategy: {d.get('strategy', result.get('strategy', 'both'))}",
        f"Timeframe: {result.get('interval', 'N/A')}",
        f"Session: {session}",
        f"Trend: {trend}",
        f"Confluence Score: {d.get('score', d.get('weighted_score', 'N/A'))}",
        f"Confirmation reason: {confirmation_reason}",
    ]
    mtf_ctx = result.get("mtf")
    if mtf_ctx:
        tfs = mtf_ctx.get("timeframes", {})
        style_label = mtf_ctx.get("trading_style", "intraday")
        used = mtf_ctx.get("timeframes_used") or []
        if used:
            lines.append(f"Trading style: {style_label} ({' -> '.join(used)})")
        else:
            lines.append(
                f"Timeframes: {tfs.get('parent', ['4H'])} bias -> "
                f"{tfs.get('structure', ['1H'])} structure -> {tfs.get('entry', '30min')} entry"
            )
        liq = mtf_ctx.get("h1_liquidity") or {}
        if liq:
            lines.append(
                f"1H liquidity: {len(liq.get('above', []))} pool(s) above, "
                f"{len(liq.get('below', []))} below"
            )
        if mtf_ctx.get("liquidity_draw"):
            draw = mtf_ctx["liquidity_draw"]
            lines.append(f"Draw on liquidity: {draw['level']} ({draw['pips_away']} pips away)")
    lines += [
        f"Confidence detail: rules {d.get('rule_confidence', d.get('confidence', 0)):.0%}"
        + (f", ML {d['ml_confidence']:.0%}" if d.get("ml_confidence") is not None else ""),
        f"Scores: bullish {d['scores']['bullish']} vs bearish {d['scores']['bearish']} "
        f"({d['confluences']} valid confluences)",
    ]
    has_levels = d.get("entry") is not None and d.get("stop_loss") is not None
    if d["action"] == confluence.ACTION_WAIT:
        lines.append("Setup forming — wait for confirmation before acting.")
        if has_levels:
            lines.append("Levels below apply once the setup confirms:")
    if has_levels and (confluence.is_trade_action(d["action"]) or d["action"] == confluence.ACTION_WAIT):
        sl_extra = (
            f" ({d['sl_pips']} pips / {d['sl_pct']}%)"
            if d.get("sl_pips") is not None else ""
        )
        tp_extra = (
            f" ({d['tp_pips']} pips / {d['tp_pct']}%)"
            if d.get("tp_pips") is not None else ""
        )
        lines += [
            f"Level distances: SL{sl_extra or ' N/A'} | TP{tp_extra or ' N/A'}",
        ]
        if calc and all(
            key in calc for key in (
                "balance", "risk_pct", "risk_amount", "reward_amount",
                "pip_value_per_lot_usd", "sl_pips", "tp_pips",
            )
        ):
            approx = " (approx.)" if calc.get("approximate") else ""
            lines += [
                "",
                f"{b}Position calculator{b} (balance ${calc['balance']:g}, risk {calc['risk_pct']:g}%):",
                f"- Lot size: {calc['lot_size']} (risk ${calc['risk_amount']}, reward ${calc['reward_amount']}){approx}",
                f"- Pip value/lot: ${calc['pip_value_per_lot_usd']} | SL {calc['sl_pips']} pips | TP {calc['tp_pips']} pips",
            ]
            if calc.get("warning"):
                lines.append(f"- WARNING: {calc['warning']}")
    if d.get("killzone"):
        lines.append(f"Kill zone: {d['killzone']}")
    lines.append("")
    lines.append(f"{b}Why:{b}")
    lines += [f"- {r}" for r in d["reasoning"]]
    if d["vetoes"]:
        lines.append(f"{b}Vetoes:{b}")
        lines += [f"- {v}" for v in d["vetoes"]]
    if result.get("ml"):
        ml = result["ml"]
        if isinstance(ml, dict) and "samples" in ml:
            lines.append(
                f"Model: {ml['samples']} samples, "
                f"val accuracy {ml.get('val_accuracy', 0):.1%}"
            )
        elif isinstance(ml, dict) and ml.get("meta_ml_probability") is not None:
            lines.append(f"Meta-ML P(win): {ml['meta_ml_probability']:.0%}")
        elif isinstance(ml, dict) and not ml.get("has_active_model"):
            lines.append("Meta-model: rule-only (no active version)")
    lines.append(
        f"Data: {result['candles']} candles ({result['data_source']}), last {result['last_candle']}"
    )
    lines.append(d.get("disclaimer", "Not financial advice."))
    return "\n".join(lines)
