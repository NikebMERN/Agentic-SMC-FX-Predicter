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
import threading
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

_save_locks_guard = threading.Lock()
_save_locks: dict[str, threading.Lock] = {}


def _save_lock(path: str) -> threading.Lock:
    with _save_locks_guard:
        lock = _save_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _save_locks[path] = lock
        return lock


def _atomic_joblib_dump(payload: dict, path: str) -> None:
    """Write model atomically — avoids Windows Errno 22 on concurrent overwrites."""
    import time

    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    last_exc: OSError | None = None
    for attempt in range(5):
        tmp = os.path.join(directory, f".{os.path.basename(path)}.{os.getpid()}.{attempt}.tmp")
        try:
            joblib.dump(payload, tmp)
            os.replace(tmp, path)
            return
        except OSError as exc:
            last_exc = exc
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            time.sleep(0.15 * (attempt + 1))
    if last_exc:
        raise last_exc


def model_path(symbol: str, interval: str) -> str:
    return os.path.join(MODEL_DIR, f"{symbol.upper()}_{interval}.joblib")


VERSIONS_DIR = os.path.join(MODEL_DIR, "versions")


def versioned_model_path(symbol: str, interval: str) -> str:
    """Unique file per training run so every version stays usable forever."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(VERSIONS_DIR, f"{symbol.upper()}_{interval}_{stamp}.joblib")


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
    path = model_path(symbol, interval)
    with _save_lock(path):
        return _train_and_predict_locked(symbol, df, interval, auto_promote=auto_promote, use_feedback=use_feedback, path=path)


def _train_and_predict_locked(
    symbol: str,
    df: pd.DataFrame,
    interval: str,
    *,
    auto_promote: bool,
    use_feedback: bool,
    path: str,
) -> dict | None:
    """Inner train/save — caller must hold _save_lock(path)."""
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
    payload = {
        "model": model,
        "feature_names": list(X.columns),
        "metrics": metrics,
        "symbol": symbol.upper(),
        "interval": interval,
    }
    # "latest" pointer file (legacy path, always the newest weights)...
    _atomic_joblib_dump(payload, path)
    # ...plus an immutable per-version copy the admin can re-activate later.
    version_path = versioned_model_path(symbol, interval)
    _atomic_joblib_dump(payload, version_path)

    active = get_active_model_version(symbol, interval)
    promote = auto_promote and (active is None or val_accuracy > (active.val_accuracy or 0.0))

    if promote and feedback_ids:
        mark_samples_used(feedback_ids)
        mark_training_records_used(feedback_ids)

    save_model_version(symbol, interval, version_path, metrics, promote=promote)
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


def predict_with_active_model(symbol: str, df: pd.DataFrame, interval: str) -> dict | None:
    """Predict the latest candle with the admin-ACTIVATED model version.

    This is what lets the admin pin any previously trained model: no
    retraining happens — the saved weights are loaded and used as-is.
    Returns None when no active version exists (caller falls back to
    fresh training). Feature columns are aligned by name so models
    survive feature-set evolution.
    """
    active = get_active_model_version(symbol, interval)
    if not active or not active.path or not os.path.exists(active.path):
        return None
    try:
        payload = joblib.load(active.path)
        model = payload["model"]
        feature_names = payload.get("feature_names") or []
    except Exception as exc:
        log.warning("%s: active model version %s unreadable: %s", symbol, active.id, exc)
        return None

    X, _ = build_dataset(df)
    latest = X.iloc[[-1]]
    if latest.isna().any(axis=1).iloc[0]:
        clean = X[X.notna().all(axis=1)]
        if clean.empty:
            return None
        latest = clean.iloc[[-1]]
    latest = latest.reindex(columns=feature_names, fill_value=0.0).fillna(0.0)

    proba_row = model.predict_proba(latest)[0]
    proba = {cls: float(p) for cls, p in zip(model.classes_, proba_row)}
    for cls in ("up", "down", "flat"):
        proba.setdefault(cls, 0.0)
    direction = max(proba, key=proba.get)

    metrics = dict(payload.get("metrics") or {})
    metrics["mode"] = "saved_version"
    metrics["version_id"] = active.id
    log.info(
        "%s: predicted with saved model version %s (val_accuracy %s) -> %s",
        symbol, active.id, metrics.get("val_accuracy"), direction,
    )
    return {
        "proba": proba,
        "direction": direction,
        "metrics": metrics,
        "model_path": active.path,
        "version_id": active.id,
    }


def retrain_with_feedback(symbol: str, df: pd.DataFrame, interval: str, promote: bool = True) -> dict | None:
    """Admin-triggered retrain that uses feedback and optionally promotes."""
    result = train_and_predict(symbol, df, interval, auto_promote=promote, use_feedback=True)
    if result and promote and result.get("feedback_ids"):
        mark_samples_used(result["feedback_ids"])
    elif result and not promote and result.get("feedback_ids"):
        pass  # keep feedback pending until promotion
    return result
