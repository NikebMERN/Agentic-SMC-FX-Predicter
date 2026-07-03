# tests/test_pipeline.py
"""End-to-end engine tests on synthetic data: features, training,
confluence decision invariants, full pipeline."""
import os

import pytest

from engine.features import HORIZON, build_dataset


def test_dataset_shapes_and_labels(synthetic_ohlc):
    X, y = build_dataset(synthetic_ohlc)
    assert len(X) == len(synthetic_ohlc) == len(y)
    assert X.shape[1] >= 15
    # the last HORIZON rows have features but no label (that's the live edge)
    assert y.iloc[-HORIZON:].isna().all()
    assert set(y.dropna().unique()) <= {"up", "down", "flat"}


def test_train_and_predict_returns_calibrated_probabilities(synthetic_ohlc):
    from engine.model_trainer import model_path, train_and_predict
    result = train_and_predict("TSTUSD", synthetic_ohlc, "60min")
    assert result is not None
    proba = result["proba"]
    assert set(proba) == {"up", "down", "flat"}
    assert sum(proba.values()) == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < result["metrics"]["val_accuracy"] <= 1.0
    path = model_path("TSTUSD", "60min")
    assert os.path.exists(path)
    os.remove(path)


def test_predict_symbol_full_pipeline(synthetic_csv):
    from engine.pipeline import format_result_text, predict_symbol

    stages = []
    result = predict_symbol(
        "TSTUSD", fetch=False, on_progress=lambda stage, msg: stages.append(stage)
    )

    assert {"fetch", "data", "analyze", "train", "decide", "done"} <= set(stages)
    from engine.confluence import ACTION_BUY, ACTION_NO_TRADE, ACTION_SELL, ACTION_WAIT, is_trade_action
    decision = result["decision"]
    assert decision["action"] in (ACTION_BUY, ACTION_SELL, ACTION_NO_TRADE, ACTION_WAIT, "BUY", "SELL")
    assert 0.0 <= decision["confidence"] <= 1.0
    assert isinstance(decision["reasoning"], list) and decision["reasoning"]
    assert "component_scores" in decision
    assert "disclaimer" in decision

    if is_trade_action(decision["action"]) or decision["action"] in (ACTION_BUY, ACTION_SELL):
        if decision["action"] in (ACTION_BUY, "BUY"):
            assert decision["stop_loss"] < decision["entry"] < decision["take_profit"]
        else:
            assert decision["take_profit"] < decision["entry"] < decision["stop_loss"]
    elif decision["action"] in (ACTION_NO_TRADE, "NO_TRADE"):
        assert decision["vetoes"] or decision.get("no_trade_reasons")

    text = format_result_text(result)
    assert "TSTUSD" in text and decision["action"] in text

    from engine.model_trainer import model_path
    if os.path.exists(model_path("TSTUSD", "60min")):
        os.remove(model_path("TSTUSD", "60min"))


def test_invalid_symbol_rejected():
    from engine.data import normalize_symbol
    for bad in ("EUR", "EURUSD1", "DROP TABLE", ""):
        with pytest.raises(ValueError):
            normalize_symbol(bad)
    assert normalize_symbol(" eur/usd ") == "EURUSD"


def test_train_skipped_when_insufficient_samples():
    from engine.model_trainer import train_and_predict
    import pandas as pd
    import numpy as np

    idx = pd.date_range("2025-01-01", periods=50, freq="h")
    close = np.linspace(1.1, 1.11, 50)
    df = pd.DataFrame(
        {"Open": close, "High": close + 0.001, "Low": close - 0.001,
         "Close": close, "Volume": 0.0},
        index=idx,
    )
    assert train_and_predict("SMALL", df, "60min") is None
