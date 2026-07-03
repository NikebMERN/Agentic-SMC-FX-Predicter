# tests/test_backtest.py
import numpy as np
import pandas as pd

from engine.backtest import run_backtest


def test_backtest_runs_on_synthetic_data():
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    close = np.linspace(1.10, 1.15, n) + np.random.default_rng(42).normal(0, 0.0002, n)
    df = pd.DataFrame(
        {"Open": close, "High": close + 0.001, "Low": close - 0.001,
         "Close": close, "Volume": 0.0},
        index=idx,
    )
    result = run_backtest(df, "TSTUSD", max_bars=200)
    assert "trades" in result
    assert result["symbol"] == "TSTUSD"
