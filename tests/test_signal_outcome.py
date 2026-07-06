"""Tests for signal outcome evaluation."""
import pandas as pd

from ml.labels import OUTCOME_SL_BEFORE_TP, evaluate_tp_sl_path


def test_bearish_sl_before_tp():
    df = pd.DataFrame({
        "Open": [1.0, 1.01, 1.02],
        "High": [1.01, 1.03, 1.04],
        "Low": [0.99, 1.0, 1.01],
        "Close": [1.0, 1.02, 1.03],
    })
    outcome, _, _ = evaluate_tp_sl_path(
        df, direction="bearish", entry=1.0, tp=0.95, sl=1.02,
    )
    assert outcome == OUTCOME_SL_BEFORE_TP
