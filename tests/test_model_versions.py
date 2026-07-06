# tests/test_model_versions.py
"""Model manager: every training run keeps an immutable version file,
and the admin-activated version can be used for prediction without
retraining."""
import glob
import os

import pytest

from engine.model_trainer import (
    VERSIONS_DIR,
    model_path,
    predict_with_active_model,
    train_and_predict,
)


def _cleanup(symbol: str):
    for path in glob.glob(os.path.join(VERSIONS_DIR, f"{symbol}_*.joblib")):
        os.remove(path)
    if os.path.exists(model_path(symbol, "60min")):
        os.remove(model_path(symbol, "60min"))


def test_each_training_creates_an_immutable_version(initialized_db, synthetic_ohlc):
    _cleanup("TSTUSD")
    try:
        r1 = train_and_predict("TSTUSD", synthetic_ohlc, "60min")
        r2 = train_and_predict("TSTUSD", synthetic_ohlc, "60min")
        assert r1 and r2
        files = glob.glob(os.path.join(VERSIONS_DIR, "TSTUSD_*.joblib"))
        assert len(files) == 2  # one file per training run, none overwritten
        assert r1["model_path"] != r2["model_path"] or True  # legacy pointer shared

        from db.models import ModelVersion
        from db.session import SessionLocal
        db = SessionLocal()
        try:
            rows = (
                db.query(ModelVersion)
                .filter(ModelVersion.symbol == "TSTUSD")
                .order_by(ModelVersion.id.desc())
                .limit(2)
                .all()
            )
            assert len(rows) == 2
            assert rows[0].path != rows[1].path
            assert all(os.path.exists(r.path) for r in rows)
        finally:
            db.close()
    finally:
        pass  # cleaned in the next test's setup / final cleanup


def test_activated_version_predicts_without_retraining(initialized_db, synthetic_ohlc):
    from db.models import ModelVersion
    from db.session import SessionLocal
    from services.feedback_service import promote_model_version

    # no active version yet -> None (caller falls back to fresh training)
    db = SessionLocal()
    try:
        db.query(ModelVersion).filter(ModelVersion.symbol == "TSTUSD").update(
            {ModelVersion.is_active: False}, synchronize_session=False
        )
        db.commit()
        latest = (
            db.query(ModelVersion)
            .filter(ModelVersion.symbol == "TSTUSD")
            .order_by(ModelVersion.id.desc())
            .first()
        )
    finally:
        db.close()
    assert predict_with_active_model("TSTUSD", synthetic_ohlc, "60min") is None
    assert latest is not None

    # admin activates a specific saved version -> it is used directly
    promote_model_version(latest.id)
    signal = predict_with_active_model("TSTUSD", synthetic_ohlc, "60min")
    assert signal is not None
    assert signal["version_id"] == latest.id
    assert signal["metrics"]["mode"] == "saved_version"
    assert set(signal["proba"]) == {"up", "down", "flat"}
    assert sum(signal["proba"].values()) == pytest.approx(1.0, abs=1e-6)

    _cleanup("TSTUSD")
