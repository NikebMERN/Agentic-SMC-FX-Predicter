"""Nightly meta-model retraining with Redis distributed lock."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

import pandas as pd

from db.models import BacktestRun, TrainingRecord, TrainingRun
from db.session import SessionLocal
from ml.backtest_model import run_walk_forward_backtest
from ml.promotion_gate import evaluate_promotion
from ml.recency import calculate_sample_weight
from ml.train_model import available_model_types, train_candidate
from services.ml_service import get_active_model, promote_version, save_candidate_version
from services.pair_performance import aggregate_pair_performance
from utils import settings
from utils.config import SUPPORTED_PAIRS
from utils.logger import get_logger

log = get_logger("services.nightly_retrain")

LOCK_KEY = "smc:nightly_retrain"
LOCK_TTL = 3600


def _redis_client():
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def acquire_lock() -> bool:
    client = _redis_client()
    if not client:
        return True  # no redis — single-process fallback
    try:
        return bool(client.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL))
    except Exception as exc:
        log.warning("Redis lock unavailable: %s", exc)
        return True


def release_lock():
    client = _redis_client()
    if client:
        try:
            client.delete(LOCK_KEY)
        except Exception:
            pass


def _load_training_records() -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(TrainingRecord)
            .filter(TrainingRecord.admin_status == "APPROVED")
            .order_by(TrainingRecord.created_at.asc())
            .all()
        )
        records = []
        for row in rows:
            try:
                feats = json.loads(row.features_json or "{}")
            except json.JSONDecodeError:
                continue
            label_raw = row.final_label or row.label
            if label_raw in ("up", "correct", "1", 1):
                label = 1
            elif label_raw in ("down", "wrong", "0", 0):
                label = 0
            else:
                continue
            meta = feats.get("meta_features") or feats
            if isinstance(meta, dict) and len(meta) >= 8:
                feature_dict = {k: v for k, v in meta.items() if k not in ("schema_version", "symbol")}
            else:
                feature_dict = {k: v for k, v in feats.items() if isinstance(v, (int, float, bool))}
            if len(feature_dict) < 5:
                continue
            records.append({
                "symbol": row.symbol,
                "interval": row.interval or "60min",
                "trading_style": feats.get("trading_style", "intraday"),
                "date": row.created_at or datetime.utcnow(),
                "features": feature_dict,
                "label": label,
                "weight": calculate_sample_weight(row.created_at or datetime.utcnow()),
            })
        return records
    finally:
        db.close()


def _group_records(records: list[dict]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list] = {}
    for rec in records:
        key = (rec["symbol"], rec["interval"], rec["trading_style"])
        groups.setdefault(key, []).append(rec)
    return groups


def run_retrain(*, run_type: str = "NIGHTLY", pairs: list[str] | None = None) -> dict:
    if not acquire_lock():
        return {"status": "SKIPPED", "reason": "lock_held"}

    db = SessionLocal()
    run = TrainingRun(run_type=run_type, status="RUNNING", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    db.close()

    models_created = 0
    models_promoted = 0
    pairs_processed = 0
    errors: list[str] = []

    try:
        records = _load_training_records()
        groups = _group_records(records)
        target_pairs = pairs or list(settings.get_supported_pairs() or SUPPORTED_PAIRS)

        for symbol in target_pairs:
            for interval in ("60min", "30min", "15min"):
                for style in ("intraday", "scalping", "swing"):
                    key = (symbol.upper(), interval, style)
                    group = groups.get(key, [])
                    if len(group) < 30:
                        continue

                    pairs_processed += 1
                    try:
                        result = _train_pair_group(key, group)
                        if result:
                            models_created += 1
                            if result.get("promoted"):
                                models_promoted += 1
                    except Exception as exc:
                        log.exception("Retrain failed for %s", key)
                        errors.append(f"{key}: {exc}")

        status = "COMPLETED" if not errors else "COMPLETED_WITH_ERRORS"
        _finalize_run(run_id, status, pairs_processed, models_created, models_promoted, errors)
        return {
            "run_id": run_id,
            "status": status,
            "pairs_processed": pairs_processed,
            "models_created": models_created,
            "models_promoted": models_promoted,
            "errors": errors,
        }
    except Exception as exc:
        log.exception("Nightly retrain failed")
        _finalize_run(run_id, "FAILED", pairs_processed, models_created, models_promoted, [str(exc)])
        return {"run_id": run_id, "status": "FAILED", "error": str(exc)}
    finally:
        release_lock()


def _train_pair_group(key: tuple, group: list[dict]) -> dict | None:
    symbol, interval, style = key
    feature_cols = list(group[0]["features"].keys())
    df = pd.DataFrame([{**r["features"], "label": r["label"]} for r in group])
    weights = [r["weight"] for r in group]
    import numpy as np
    w = np.array(weights)

    wf_metrics = run_walk_forward_backtest(group)
    best_result = None
    best_type = "RANDOM_FOREST"
    for model_type in available_model_types():
        result = train_candidate(df[feature_cols], df["label"].astype(int), model_type=model_type, sample_weight=w)
        if result and (best_result is None or result["metrics"].get("f1", 0) > best_result["metrics"].get("f1", 0)):
            best_result = result
            best_type = model_type

    if not best_result:
        return None

    metrics = {**best_result["metrics"], **{k: v for k, v in wf_metrics.items() if k != "window_metrics"}}
    version = save_candidate_version(
        symbol=symbol,
        interval=interval,
        trading_style=style,
        model_type=best_type,
        train_result=best_result,
        metrics=metrics,
        training_record_count=len(group),
        training_data_start=group[0]["date"],
        training_data_end=group[-1]["date"],
    )
    if not version:
        return None

    db = SessionLocal()
    try:
        db.add(BacktestRun(
            model_version_id=version.id,
            symbol=symbol,
            interval=interval,
            trading_style=style,
            walk_forward_windows=wf_metrics.get("windows", 0),
            total_signals=wf_metrics.get("total_signals", 0),
            accepted_signals=wf_metrics.get("accepted_signals", 0),
            rejected_signals=wf_metrics.get("rejected_signals", 0),
            win_rate=wf_metrics.get("win_rate"),
            precision=wf_metrics.get("precision"),
            recall=wf_metrics.get("recall"),
            f1=wf_metrics.get("f1"),
            brier_score=wf_metrics.get("brier_score"),
            passed_promotion_gate=False,
        ))
        db.commit()
    finally:
        db.close()

    active = get_active_model(symbol, interval, style)
    active_metrics = None
    if active and active.metrics_json:
        try:
            active_metrics = json.loads(active.metrics_json)
        except json.JSONDecodeError:
            pass

    promo = evaluate_promotion(metrics, active_metrics)
    promoted = False
    if promo["passed"]:
        promoted = promote_version(version.id)
        db = SessionLocal()
        try:
            bt = db.query(BacktestRun).filter(BacktestRun.model_version_id == version.id).first()
            if bt:
                bt.passed_promotion_gate = True
                db.commit()
        finally:
            db.close()

    aggregate_pair_performance(symbol, interval, style, version.id if promoted else None)
    return {"version_id": version.id, "promoted": promoted, "promotion": promo}


def _finalize_run(run_id, status, pairs_processed, models_created, models_promoted, errors):
    db = SessionLocal()
    try:
        run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
        if run:
            run.status = status
            run.completed_at = datetime.utcnow()
            run.pairs_processed = pairs_processed
            run.models_created = models_created
            run.models_promoted = models_promoted
            run.error_message = "\n".join(errors[:20]) if errors else None
            run.metadata_json = json.dumps({"errors": errors})
            db.commit()
    finally:
        db.close()


def list_training_runs(limit: int = 30) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "run_type": r.run_type,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "pairs_processed": r.pairs_processed,
                "models_created": r.models_created,
                "models_promoted": r.models_promoted,
                "error_message": r.error_message,
            }
            for r in rows
        ]
    finally:
        db.close()
