# tests/test_backtest_cli.py
import json
import os

import pandas as pd
import pytest


def test_backtest_cli_writes_report(synthetic_ohlc, monkeypatch):
    from engine.data import DATA_DIR
    from utils.config import INTERVAL

    path = os.path.join(DATA_DIR, f"TSTUSD_{INTERVAL}.csv")
    synthetic_ohlc.to_csv(path)

    class Args:
        symbol = "TSTUSD"

    from run import cmd_backtest

    try:
        code = cmd_backtest(Args())
        assert code == 0
        report_path = os.path.join(os.path.dirname(__file__), "..", "logs", "backtest_report.json")
        assert os.path.isfile(report_path)
        with open(report_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert "pairs" in data
        assert "generated_at" in data
        assert isinstance(data["pairs"], list)
        assert data["pairs"]
        first = data["pairs"][0]
        for key in ("symbol", "trades", "win_rate", "avg_rr", "max_drawdown_pct"):
            assert key in first
    finally:
        if os.path.exists(path):
            os.remove(path)
