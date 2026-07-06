"""Probability calibration selection and fitting."""
from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def choose_calibration_method(n_samples: int) -> str:
    return "isotonic" if n_samples >= 500 else "sigmoid"


def build_calibrator(base_estimator, X, y, *, method: str | None = None):
    method = method or choose_calibration_method(len(y))
    return CalibratedClassifierCV(base_estimator, method=method, cv=3)


def fit_calibrated(base_estimator, X, y, sample_weight=None):
    method = choose_calibration_method(len(y))
    cal = build_calibrator(base_estimator, X, y, method=method)
    cal.fit(X, y, sample_weight=sample_weight)
    return cal, method
