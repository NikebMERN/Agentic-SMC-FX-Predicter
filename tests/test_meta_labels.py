"""Tests for TP/SL meta labels."""
import pandas as pd

from ml.labels import (
    OUTCOME_SL_BEFORE_TP,
    OUTCOME_TP_BEFORE_SL,
    evaluate_tp_sl_path,
    outcome_to_meta_label,
)


def test_outcome_to_meta_label():
    assert outcome_to_meta_label(OUTCOME_TP_BEFORE_SL) == 1
    assert outcome_to_meta_label(OUTCOME_SL_BEFORE_TP) == 0
    assert outcome_to_meta_label("NEUTRAL") is None


def test_bullish_tp_before_sl():
    df = pd.DataFrame({
        "Open": [1.0, 1.01, 1.02],
        "High": [1.01, 1.03, 1.05],
        "Low": [0.99, 1.0, 1.01],
        "Close": [1.0, 1.02, 1.04],
    })
    outcome, mfe, mae = evaluate_tp_sl_path(
        df, direction="bullish", entry=1.0, tp=1.03, sl=0.98,
    )
    assert outcome == OUTCOME_TP_BEFORE_SL
    assert mfe > 0
