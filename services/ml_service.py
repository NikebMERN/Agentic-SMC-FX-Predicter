"""Active meta-model lookup and prediction."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func

from db.models import ModelVersion
from db.session import SessionLocal
from ml.model_registry import load_bundle, save_bundle
from ml.predict_quality import predict_quality
from ml.train_model import train_candidate
from schemas.meta_feature_schema import MetaFeatureSnapshot
from utils.logger import get_logger

log = get_logger("services.ml_service")


def get_active_model(
    symbol: str,
    interval: str,
    trading_style: str = "intraday",
) -> ModelVersion | None:
    db = SessionLocal()
    try:
        return (
            db.query(ModelVersion)
            .filter(
                ModelVersion.symbol == symbol.upper(),
                ModelVersion.interval == interval,
                ModelVersion.trading_style == trading_style,
                ModelVersion.status == "ACTIVE",
            )
            .order_by(
                func.coalesce(ModelVersion.promoted_at, datetime(1970, 1, 1)).desc(),
                ModelVersion.id.desc(),
            )
            .first()
        )
    finally:
        db.close()


def load_active_bundle(symbol: str, interval: str, trading_style: str = "intraday") -> dict | None:
    row = get_active_model(symbol, interval, trading_style)
    if not row:
        return None
    bundle = load_bundle(row.id)
    if bundle:
        bundle["version_id"] = row.id
        bundle["model_version"] = row
    return bundle


def predict_meta_quality(
    features: MetaFeatureSnapshot,
    symbol: str,
    interval: str,
    trading_style: str = "intraday",
) -> tuple[float | None, int | None]:
    try:
        bundle = load_active_bundle(symbol, interval, trading_style)
        if not bundle:
            return None, None
        prob = predict_quality(bundle, features)
        return prob, bundle.get("version_id")
    except Exception:
        log.exception("Meta quality lookup failed for %s/%s", symbol, interval)
        return None, None


def save_candidate_version(
    *,
    symbol: str,
    interval: str,
    trading_style: str,
    model_type: str,
    train_result: dict,
    metrics: dict,
    threshold_version_id: int | None = None,
    training_record_count: int = 0,
    training_data_start: datetime | None = None,
    training_data_end: datetime | None = None,
    status: str = "CANDIDATE",
) -> ModelVersion | None:
    db = SessionLocal()
    try:
        row = ModelVersion(
            symbol=symbol.upper(),
            interval=interval,
            trading_style=trading_style,
            model_type=model_type,
            path="",
            status=status,
            threshold_version_id=threshold_version_id,
            training_record_count=training_record_count,
            training_data_start=training_data_start,
            training_data_end=training_data_end,
            walk_forward_score=metrics.get("walk_forward_score"),
            precision=metrics.get("precision"),
            recall=metrics.get("recall"),
            f1=metrics.get("f1"),
            brier_score=metrics.get("brier_score"),
            log_loss=metrics.get("log_loss"),
            win_rate=metrics.get("win_rate"),
            val_accuracy=metrics.get("val_accuracy", 0),
            samples=metrics.get("samples", training_record_count),
            metrics_json=json.dumps(metrics),
            trained_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        row.display_name = _default_display_name(row.id)

        paths = save_bundle(
            row.id,
            model=train_result["base_estimator"],
            calibrator=train_result["calibrator"],
            feature_names=train_result["feature_names"],
            metrics=metrics,
        )
        row.path = paths["model_path"]
        row.calibrator_path = paths["calibrator_path"]
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        log.exception("Failed to save candidate model")
        db.rollback()
        return None
    finally:
        db.close()


def promote_version(version_id: int) -> bool:
    db = SessionLocal()
    try:
        candidate = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
        if not candidate:
            return False
        active_rows = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.symbol == candidate.symbol,
                ModelVersion.interval == candidate.interval,
                ModelVersion.trading_style == candidate.trading_style,
                ModelVersion.status == "ACTIVE",
            )
            .all()
        )
        for row in active_rows:
            row.status = "ARCHIVED"
            row.is_active = False
        candidate.status = "ACTIVE"
        candidate.is_active = True
        candidate.promoted_at = datetime.utcnow()
        db.commit()
        return True
    except Exception:
        log.exception("Promote failed for version %s", version_id)
        db.rollback()
        return False
    finally:
        db.close()


def list_model_versions(
    symbol: str | None = None,
    interval: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(ModelVersion).order_by(ModelVersion.created_at.desc())
        if symbol:
            q = q.filter(ModelVersion.symbol == symbol.upper())
        if interval:
            q = q.filter(ModelVersion.interval == interval)
        rows = q.limit(limit).all()
        return [_serialize_version(r) for r in rows]
    finally:
        db.close()


def _serialize_version(row: ModelVersion) -> dict:
    try:
        metrics = json.loads(row.metrics_json) if row.metrics_json else {}
    except (json.JSONDecodeError, TypeError):
        metrics = {}
    return {
        "id": row.id,
        "name": row.display_name or _default_display_name(row.id),
        "symbol": row.symbol,
        "interval": row.interval,
        "trading_style": row.trading_style,
        "model_type": row.model_type,
        "status": row.status,
        "is_active": row.is_active,
        "walk_forward_score": row.walk_forward_score,
        "precision": row.precision,
        "recall": row.recall,
        "f1": row.f1,
        "brier_score": row.brier_score,
        "win_rate": row.win_rate,
        "samples": row.samples,
        "val_accuracy": row.val_accuracy,
        "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "metrics": metrics,
    }


def _default_display_name(version_id: int) -> str:
    position = max(int(version_id) - 1, 0)
    return f"Model {position // 10 + 1}.{position % 10}"
