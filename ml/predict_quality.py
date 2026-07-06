"""Load active meta-model and predict calibrated P(win)."""
from __future__ import annotations

import pandas as pd

from ml.model_registry import load_bundle
from schemas.meta_feature_schema import MetaFeatureSnapshot


def predict_quality(
    bundle: dict,
    features: MetaFeatureSnapshot | dict,
) -> float | None:
    cal = bundle.get("calibrator") or bundle.get("model")
    if cal is None:
        return None

    if isinstance(features, MetaFeatureSnapshot):
        vec = features.feature_vector()
    else:
        vec = features

    names = bundle.get("feature_names") or list(vec.keys())
    row = {n: vec.get(n, 0) for n in names}
    X = pd.DataFrame([row])
    try:
        proba = cal.predict_proba(X)[0]
        if len(proba) >= 2:
            return float(proba[1])
        return float(proba[0])
    except Exception:
        return None


def load_and_predict(version_id: int | str, features: MetaFeatureSnapshot | dict) -> float | None:
    bundle = load_bundle(version_id)
    if not bundle:
        return None
    return predict_quality(bundle, features)
