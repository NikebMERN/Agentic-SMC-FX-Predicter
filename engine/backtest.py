# engine/backtest.py
"""Walk-forward backtest of the confluence engine over historical CSV data."""
import pandas as pd

from engine import confluence
from utils.logger import get_logger

log = get_logger("engine.backtest")

STEP_BARS = 12
MIN_WARMUP = 100


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    max_bars: int = 800,
    use_ml: bool = False,
) -> dict:
    """Simulate rule-based decisions every STEP_BARS bars."""
    df = df.tail(max_bars).copy()
    if len(df) < MIN_WARMUP + 50:
        return {"error": "Not enough bars for backtest", "trades": 0}

    trades = []
    equity = 10000.0
    peak = equity
    max_drawdown = 0.0

    for end in range(MIN_WARMUP, len(df) - 20, STEP_BARS):
        window = df.iloc[: end + 1]
        analysis = confluence.analyze(window, symbol)
        decision = confluence.decide(analysis, ml_signal=None)
        from engine.confluence import is_trade_action, trade_side_from_action
        if not is_trade_action(decision["action"]):
            continue
        side = trade_side_from_action(decision["action"])
        entry = decision["entry"]
        sl = decision["stop_loss"]
        tp = decision["take_profit"]
        if not entry or not sl or not tp:
            continue

        outcome = None
        exit_price = entry
        for j in range(end + 1, min(end + 21, len(df))):
            bar = df.iloc[j]
            hi, lo = float(bar["High"]), float(bar["Low"])
            if side == "BUY":
                if lo <= sl:
                    outcome, exit_price = "loss", sl
                    break
                if hi >= tp:
                    outcome, exit_price = "win", tp
                    break
            else:
                if hi >= sl:
                    outcome, exit_price = "loss", sl
                    break
                if lo <= tp:
                    outcome, exit_price = "win", tp
                    break

        if outcome is None:
            continue

        risk = abs(entry - sl)
        reward = abs(exit_price - entry)
        rr = reward / risk if risk > 0 else 0
        pnl_pct = (reward if outcome == "win" else -risk) / entry * 100
        equity += equity * (pnl_pct / 100) * 0.01
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, dd)
        trades.append({"outcome": outcome, "rr": round(rr, 2), "action": decision["action"]})

    wins = sum(1 for t in trades if t["outcome"] == "win")
    total = len(trades)
    return {
        "symbol": symbol.upper(),
        "bars_tested": len(df),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total, 4) if total else 0.0,
        "avg_rr": round(sum(t["rr"] for t in trades) / total, 2) if total else 0.0,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "final_equity": round(equity, 2),
    }
