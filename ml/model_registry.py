"""Model artifact persistence."""
from __future__ import annotations

import json
import os
import time

import joblib

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_ARTIFACT_DIR = os.environ.get("MODEL_ARTIFACT_DIR", os.path.join(PROJECT_ROOT, "model", "artifacts"))


def artifact_dir(version_id: int | str) -> str:
    path = os.path.join(MODEL_ARTIFACT_DIR, str(version_id))
    os.makedirs(path, exist_ok=True)
    return path


def save_bundle(
    version_id: int | str,
    *,
    model,
    calibrator,
    feature_names: list[str],
    metrics: dict,
) -> dict[str, str]:
    base = artifact_dir(version_id)
    model_path = os.path.join(base, "model.joblib")
    cal_path = os.path.join(base, "calibrator.joblib")
    names_path = os.path.join(base, "feature_names.json")
    metrics_path = os.path.join(base, "metrics.json")

    _atomic_dump(model, model_path)
    _atomic_dump(calibrator, cal_path)
    with open(names_path, "w", encoding="utf-8") as fh:
        json.dump(feature_names, fh)
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh)
    return {
        "model_path": model_path,
        "calibrator_path": cal_path,
        "feature_names_path": names_path,
        "metrics_path": metrics_path,
    }


def load_bundle(version_id: int | str) -> dict | None:
    base = artifact_dir(version_id)
    model_path = os.path.join(base, "model.joblib")
    if not os.path.exists(model_path):
        return None
    cal_path = os.path.join(base, "calibrator.joblib")
    names_path = os.path.join(base, "feature_names.json")
    metrics_path = os.path.join(base, "metrics.json")
    bundle = {
        "model": joblib.load(model_path),
        "calibrator": joblib.load(cal_path) if os.path.exists(cal_path) else None,
        "feature_names": json.load(open(names_path, encoding="utf-8")) if os.path.exists(names_path) else [],
        "metrics": json.load(open(metrics_path, encoding="utf-8")) if os.path.exists(metrics_path) else {},
        "model_path": model_path,
        "calibrator_path": cal_path if os.path.exists(cal_path) else None,
    }
    return bundle


def _atomic_dump(obj, path: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    for attempt in range(5):
        tmp = os.path.join(directory, f".{os.path.basename(path)}.{os.getpid()}.{attempt}.tmp")
        try:
            joblib.dump(obj, tmp)
            os.replace(tmp, path)
            return
        except OSError:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            time.sleep(0.15 * (attempt + 1))
