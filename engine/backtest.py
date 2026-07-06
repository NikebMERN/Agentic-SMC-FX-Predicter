# engine/backtest.py
"""Walk-forward backtest of the confluence engine over historical CSV data."""
import pandas as pd

from engine import confluence
from schemas.threshold_schema import SmcIctThresholds
from services.threshold_service import resolve_thresholds_model
from utils.logger import get_logger

log = get_logger("engine.backtest")

STEP_BARS = 12
MIN_WARMUP = 100


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    max_bars: int = 800,
    use_ml: bool = False,
    *,
    thresholds: SmcIctThresholds | None = None,
    trading_style: str = "intraday",
    interval: str = "60min",
) -> dict:
    """Simulate rule-based decisions every STEP_BARS bars."""
    df = df.tail(max_bars).copy()
    if len(df) < MIN_WARMUP + 50:
        return {"error": "Not enough bars for backtest", "trades": 0}

    if thresholds is None:
        thresholds = resolve_thresholds_model(symbol, interval, trading_style)

    trades = []
    no_trade = 0
    wait = 0
    invalidation_hits = 0
    bias_total = 0
    bias_correct = 0
    equity = 10000.0
    peak = equity
    max_drawdown = 0.0

    for end in range(MIN_WARMUP, len(df) - 20, STEP_BARS):
        window = df.iloc[: end + 1]
        analysis = confluence.analyze(
            window, symbol, interval=interval, thresholds=thresholds, trading_style=trading_style,
        )
        analysis["trading_style"] = trading_style
        decision = confluence.decide(analysis, ml_signal=None, thresholds=thresholds)
        action = decision["action"]
        from engine.confluence import ACTION_NO_TRADE, ACTION_WAIT, is_trade_action, trade_side_from_action

        if action == ACTION_NO_TRADE:
            no_trade += 1
            continue
        if action == ACTION_WAIT:
            wait += 1
            continue
        if not is_trade_action(action):
            continue

        side = trade_side_from_action(action)
        entry = decision["entry"]
        sl = decision["stop_loss"]
        tp = decision["take_profit"]
        if not entry or not sl or not tp:
            continue

        bias_total += 1
        outcome = None
        exit_price = entry
        hit_invalidation = False
        for j in range(end + 1, min(end + 21, len(df))):
            bar = df.iloc[j]
            hi, lo = float(bar["High"]), float(bar["Low"])
            if side == "BUY":
                if lo <= sl:
                    outcome, exit_price, hit_invalidation = "loss", sl, True
                    break
                if hi >= tp:
                    outcome, exit_price = "win", tp
                    break
            else:
                if hi >= sl:
                    outcome, exit_price, hit_invalidation = "loss", sl, True
                    break
                if lo <= tp:
                    outcome, exit_price = "win", tp
                    break

        if hit_invalidation:
            invalidation_hits += 1
        if outcome is None:
            continue

        if outcome == "win":
            bias_correct += 1

        risk = abs(entry - sl)
        reward = abs(exit_price - entry)
        rr = reward / risk if risk > 0 else 0
        pnl_pct = (reward if outcome == "win" else -risk) / entry * 100
        equity += equity * (pnl_pct / 100) * 0.01
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, dd)
        trades.append({"outcome": outcome, "rr": round(rr, 2), "action": action})

    wins = sum(1 for t in trades if t["outcome"] == "win")
    total = len(trades)
    steps = max(1, (len(df) - MIN_WARMUP - 20) // STEP_BARS)
    avg_rr = round(sum(t["rr"] for t in trades) / total, 2) if total else 0.0
    return {
        "symbol": symbol.upper(),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total, 4) if total else 0,
        "avg_rr": avg_rr,
        "accuracy": round(bias_correct / bias_total, 4) if bias_total else 0,
        "no_trade_rate": round(no_trade / steps, 4),
        "wait_rate": round(wait / steps, 4),
        "invalidation_hit_rate": round(invalidation_hits / bias_total, 4) if bias_total else 0,
        "max_drawdown": round(max_drawdown, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "final_equity": round(equity, 2),
        "trade_log": trades[:50],
    }
