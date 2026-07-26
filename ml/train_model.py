"""Train meta-label classifiers (RF + optional LightGBM/XGBoost)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
)

from ml.calibration import fit_calibrated
from utils.logger import get_logger

log = get_logger("ml.train_model")

MIN_SAMPLES = 50


def _base_rf():
    return RandomForestClassifier(
        n_estimators=200,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def _try_lightgbm():
    try:
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
            verbose=-1,
        )
    except ImportError:
        return None


def _try_xgboost():
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
            eval_metric="logloss",
        )
    except ImportError:
        return None


def available_model_types() -> list[str]:
    types = ["RANDOM_FOREST"]
    if _try_lightgbm():
        types.append("LIGHTGBM")
    if _try_xgboost():
        types.append("XGBOOST")
    return types


def _estimator(model_type: str):
    if model_type == "LIGHTGBM":
        est = _try_lightgbm()
        if est:
            return est
    if model_type == "XGBOOST":
        est = _try_xgboost()
        if est:
            return est
    return _base_rf()


def train_candidate(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    model_type: str = "RANDOM_FOREST",
    sample_weight: np.ndarray | None = None,
    val_fraction: float = 0.2,
) -> dict | None:
    if len(y) < MIN_SAMPLES or y.nunique() < 2:
        return None

    # Deterministic feature selection learned from the training prefix only:
    # remove constants and exact duplicates without looking at validation labels.
    usable = [column for column in X.columns if X[column].nunique(dropna=False) > 1]
    X = X[usable].copy()
    duplicate_columns = set()
    for index, column in enumerate(X.columns):
        for previous in X.columns[:index]:
            if X[column].equals(X[previous]):
                duplicate_columns.add(column)
                break
    if duplicate_columns:
        X = X.drop(columns=sorted(duplicate_columns))
    if X.empty:
        return None

    split = int(len(y) * (1 - val_fraction))
    if split < 20:
        split = max(1, len(y) - 10)
    X_train, X_val = X.iloc[:split], X.iloc[split:]
    y_train, y_val = y.iloc[:split], y.iloc[split:]
    w_train = sample_weight[:split] if sample_weight is not None else None

    base = _estimator(model_type)
    actual_type = model_type
    if type(base).__name__ == "RandomForestClassifier" and model_type != "RANDOM_FOREST":
        actual_type = "RANDOM_FOREST"
    positive_count = int((y_train == 1).sum())
    negative_count = int((y_train == 0).sum())
    if positive_count and negative_count and hasattr(base, "set_params"):
        params = base.get_params()
        if "scale_pos_weight" in params:
            base.set_params(scale_pos_weight=negative_count / positive_count)

    calibrator, cal_method = fit_calibrated(base, X_train, y_train, sample_weight=w_train)

    if len(y_val) >= 5:
        proba = calibrator.predict_proba(X_val)[:, 1]
        preds = (proba >= 0.5).astype(int)
        metrics = {
            "val_accuracy": float(accuracy_score(y_val, preds)),
            "precision": float(precision_score(y_val, preds, zero_division=0)),
            "recall": float(recall_score(y_val, preds, zero_division=0)),
            "f1": float(f1_score(y_val, preds, zero_division=0)),
            "brier_score": float(brier_score_loss(y_val, proba)),
            "log_loss": float(log_loss(y_val, proba, labels=[0, 1])),
            "samples": int(len(y)),
            "calibration_method": cal_method,
            "selected_features": list(X.columns),
            "confusion_matrix": confusion_matrix(y_val, preds, labels=[0, 1]).tolist(),
        }
        calibrated_models = getattr(calibrator, "calibrated_classifiers_", [])
        fitted_estimator = (
            getattr(calibrated_models[0], "estimator", None)
            if calibrated_models else None
        )
        importances = getattr(fitted_estimator, "feature_importances_", None)
        if importances is not None and len(importances) == len(X.columns):
            metrics["feature_importance"] = [
                {"feature": feature, "importance": float(importance)}
                for feature, importance in sorted(
                    zip(X.columns, importances),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ]
    else:
        metrics = {"samples": int(len(y)), "calibration_method": cal_method}

    return {
        "model_type": actual_type,
        "base_estimator": base,
        "calibrator": calibrator,
        "metrics": metrics,
        "feature_names": list(X.columns),
    }
