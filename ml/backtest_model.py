"""Walk-forward backtest aggregation for meta-models."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score

from ml.train_model import train_candidate
from ml.walk_forward import WalkForwardWindow, generate_windows


def run_walk_forward_backtest(
    records: list[dict],
    *,
    model_type: str = "RANDOM_FOREST",
    accept_threshold: float = 0.6,
) -> dict:
    """records: [{date, features: dict, label: 0|1}, ...]"""
    if len(records) < 30:
        return {"windows": 0, "passed": False, "reason": "insufficient_data"}

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    start, end = df["date"].min().to_pydatetime(), df["date"].max().to_pydatetime()
    windows = generate_windows(start, end)
    if not windows:
        return {"windows": 0, "passed": False, "reason": "no_windows"}

    feature_cols = list(records[0]["features"].keys())
    for col in feature_cols:
        df[col] = df["features"].apply(lambda f: f.get(col, 0))

    all_y, all_p, accepted = [], [], 0
    window_metrics = []

    for win in windows:
        train_mask = (df["date"] >= win.train_start) & (df["date"] < win.train_end)
        test_mask = (df["date"] >= win.test_start) & (df["date"] < win.test_end)
        train_df = df[train_mask]
        test_df = df[test_mask]
        if len(train_df) < 20 or len(test_df) < 3:
            continue

        X_train = train_df[feature_cols]
        y_train = train_df["label"].astype(int)
        result = train_candidate(X_train, y_train, model_type=model_type, val_fraction=0.15)
        if not result:
            continue

        cal = result["calibrator"]
        X_test = test_df[feature_cols]
        y_test = test_df["label"].astype(int)
        proba = cal.predict_proba(X_test)[:, 1]
        preds = (proba >= 0.5).astype(int)
        accepted += int((proba >= accept_threshold).sum())
        all_y.extend(y_test.tolist())
        all_p.extend(proba.tolist())
        window_metrics.append({
            "test_start": win.test_start.isoformat(),
            "test_end": win.test_end.isoformat(),
            "precision": float(precision_score(y_test, preds, zero_division=0)),
            "f1": float(f1_score(y_test, preds, zero_division=0)),
        })

    if not all_y:
        return {"windows": 0, "passed": False, "reason": "no_valid_windows"}

    y_arr = np.array(all_y)
    p_arr = np.array(all_p)
    preds = (p_arr >= 0.5).astype(int)
    return {
        "windows": len(window_metrics),
        "total_signals": len(all_y),
        "accepted_signals": accepted,
        "rejected_signals": len(all_y) - accepted,
        "win_rate": float(y_arr.mean()),
        "precision": float(precision_score(y_arr, preds, zero_division=0)),
        "recall": float(recall_score(y_arr, preds, zero_division=0)),
        "f1": float(f1_score(y_arr, preds, zero_division=0)),
        "brier_score": float(brier_score_loss(y_arr, p_arr)),
        "walk_forward_score": float(np.mean([w["f1"] for w in window_metrics])),
        "window_metrics": window_metrics,
        "passed": True,
    }
