# engine/model_trainer.py
"""On-demand, per-symbol model training.

Every prediction request trains a fresh model on the pair's freshest
CSV (time-ordered validation split for an honest accuracy figure, then
a refit on the full history) and immediately predicts the latest
candle. Each pair gets its own model file: model/{SYMBOL}_{interval}.joblib.

Feedback samples from closed trades and 24h reviews are merged into
training data. Models are saved as candidates — admin must promote them.
"""
import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.features import build_dataset
from services.feedback_service import (
    feedback_to_dataframe,
    get_active_model_version,
    get_approved_training_samples,
    get_pending_feedback,
    mark_samples_used,
    mark_training_records_used,
    save_model_version,
)
from utils.logger import get_logger

log = get_logger("engine.model")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "model")

MIN_SAMPLES = 150
VALIDATION_FRACTION = 0.2


def model_path(symbol: str, interval: str) -> str:
    return os.path.join(MODEL_DIR, f"{symbol.upper()}_{interval}.joblib")


def _new_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def _merge_feedback(X: pd.DataFrame, y: pd.Series, symbol: str, interval: str):
    approved = get_approved_training_samples(symbol)
    if approved:
        fb_x, fb_y, fb_ids = feedback_to_dataframe(approved, list(X.columns))
        if not fb_x.empty:
            combined_x = pd.concat([X, fb_x], ignore_index=True)
            combined_y = pd.concat([y.reset_index(drop=True), fb_y.reset_index(drop=True)], ignore_index=True)
            log.info("%s: merged %d approved training records", symbol, len(fb_ids))
            return combined_x, combined_y, fb_ids

    pending = get_pending_feedback(symbol, interval)
    if not pending:
        return X, y, []
    fb_x, fb_y, fb_ids = feedback_to_dataframe(pending, list(X.columns))
    if fb_x.empty:
        return X, y, []
    combined_x = pd.concat([X, fb_x], ignore_index=True)
    combined_y = pd.concat([y.reset_index(drop=True), fb_y.reset_index(drop=True)], ignore_index=True)
    log.info("%s: merged %d feedback samples into training set", symbol, len(fb_ids))
    return combined_x, combined_y, fb_ids


def train_and_predict(
    symbol: str,
    df: pd.DataFrame,
    interval: str,
    *,
    auto_promote: bool = False,
    use_feedback: bool = True,
) -> dict | None:
    """Train on this pair's history, save the model, predict the last candle."""
    X, y = build_dataset(df)

    labelled = y.notna() & X.notna().all(axis=1)
    X_fit, y_fit = X[labelled], y[labelled].astype(str)

    feedback_ids: list[int] = []
    if use_feedback:
        X_fit, y_fit, feedback_ids = _merge_feedback(X_fit, y_fit, symbol, interval)

    if len(X_fit) < MIN_SAMPLES:
        log.warning("%s: only %d usable samples (<%d) — skipping ML", symbol, len(X_fit), MIN_SAMPLES)
        return None
    if y_fit.nunique() < 2:
        log.warning("%s: single-class labels — skipping ML", symbol)
        return None

    split = max(1, int(len(X_fit) * (1 - VALIDATION_FRACTION)))
    model = _new_model()
    model.fit(X_fit.iloc[:split], y_fit.iloc[:split])
    val_pred = model.predict(X_fit.iloc[split:])
    val_accuracy = float(accuracy_score(y_fit.iloc[split:], val_pred))

    model = _new_model()
    model.fit(X_fit, y_fit)

    latest = X.iloc[[-1]]
    if latest.isna().any(axis=1).iloc[0]:
        latest = X[X.notna().all(axis=1)].iloc[[-1]]
    proba_row = model.predict_proba(latest)[0]
    proba = {cls: float(p) for cls, p in zip(model.classes_, proba_row)}
    for cls in ("up", "down", "flat"):
        proba.setdefault(cls, 0.0)
    direction = max(proba, key=proba.get)

    metrics = {
        "val_accuracy": round(val_accuracy, 4),
        "samples": int(len(X_fit)),
        "feedback_samples": len(feedback_ids),
        "class_counts": y_fit.value_counts().to_dict(),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(MODEL_DIR, exist_ok=True)
    path = model_path(symbol, interval)
    joblib.dump(
        {
            "model": model,
            "feature_names": list(X.columns),
            "metrics": metrics,
            "symbol": symbol.upper(),
            "interval": interval,
        },
        path,
    )

    active = get_active_model_version(symbol, interval)
    promote = auto_promote and (active is None or val_accuracy > (active.val_accuracy or 0.0))

    if promote and feedback_ids:
        mark_samples_used(feedback_ids)
        mark_training_records_used(feedback_ids)

    save_model_version(symbol, interval, path, metrics, promote=promote)
    if promote:
        log.info("%s: model promoted (val_accuracy %.3f)", symbol, val_accuracy)
    else:
        log.info(
            "%s: candidate saved (val_accuracy %.3f) — awaiting admin promotion",
            symbol, val_accuracy,
        )

    log.info(
        "%s: trained on %d samples, val accuracy %.3f, latest -> %s",
        symbol, len(X_fit), val_accuracy, direction,
    )

    return {
        "proba": proba,
        "direction": direction,
        "metrics": metrics,
        "model_path": path,
        "promoted": promote,
        "feedback_ids": feedback_ids,
    }


def retrain_with_feedback(symbol: str, df: pd.DataFrame, interval: str, promote: bool = True) -> dict | None:
    """Admin-triggered retrain that uses feedback and optionally promotes."""
    result = train_and_predict(symbol, df, interval, auto_promote=promote, use_feedback=True)
    if result and promote and result.get("feedback_ids"):
        mark_samples_used(result["feedback_ids"])
    elif result and not promote and result.get("feedback_ids"):
        pass  # keep feedback pending until promotion
    return result
