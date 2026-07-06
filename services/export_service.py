"""Background CSV/PDF export jobs with expiring downloads."""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timedelta

import pandas as pd

from db.models import ExportJob, PredictionReview
from db.session import SessionLocal
from utils.logger import get_logger

log = get_logger("services.export_service")

EXPORT_STORAGE_DIR = os.environ.get("EXPORT_STORAGE_DIR", os.path.join(os.getcwd(), "exports"))
EXPIRY_HOURS = int(os.environ.get("EXPORT_EXPIRY_HOURS", "24"))


def _ensure_dir():
    os.makedirs(EXPORT_STORAGE_DIR, exist_ok=True)


def create_export_job(
    *,
    user_id: int | None,
    export_type: str = "CSV",
    scope: str = "predictions",
    metadata: dict | None = None,
) -> ExportJob | None:
    db = SessionLocal()
    try:
        row = ExportJob(
            user_id=user_id,
            export_type=export_type.upper(),
            scope=scope,
            status="QUEUED",
            metadata_json=json.dumps(metadata or {}),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        threading.Thread(target=_process_job, args=(row.id,), daemon=True).start()
        return row
    except Exception:
        log.exception("Export job creation failed")
        db.rollback()
        return None
    finally:
        db.close()


def _process_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if not job:
            return
        job.status = "RUNNING"
        db.commit()
    finally:
        db.close()

    try:
        path = _generate_file(job_id)
        token = secrets.token_urlsafe(16)
        expires = datetime.utcnow() + timedelta(hours=EXPIRY_HOURS)
        db = SessionLocal()
        try:
            job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
            if job:
                job.status = "COMPLETED"
                job.file_path = path
                job.file_url = f"/api/exports/{job_id}/download?token={token}"
                job.expires_at = expires
                job.completed_at = datetime.utcnow()
                meta = json.loads(job.metadata_json or "{}")
                meta["download_token"] = token
                job.metadata_json = json.dumps(meta)
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        log.exception("Export job %s failed", job_id)
        db = SessionLocal()
        try:
            job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error_message = str(exc)
                db.commit()
        finally:
            db.close()


def _generate_file(job_id: int) -> str:
    _ensure_dir()
    db = SessionLocal()
    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")
        q = db.query(PredictionReview).order_by(PredictionReview.predicted_at.desc())
        if job.user_id:
            q = q.filter(PredictionReview.user_id == job.user_id)
        rows = q.limit(5000).all()
        data = [
            {
                "id": r.id,
                "symbol": r.symbol,
                "interval": r.interval,
                "action": r.predicted_action,
                "confidence": r.final_confidence or r.predicted_confidence,
                "meta_ml_probability": r.meta_ml_probability,
                "entry": r.entry_price,
                "predicted_at": r.predicted_at.isoformat() if r.predicted_at else None,
                "status": r.status,
            }
            for r in rows
        ]
    finally:
        db.close()

    ext = "csv" if job.export_type == "CSV" else "csv"
    path = os.path.join(EXPORT_STORAGE_DIR, f"export_{job_id}.{ext}")
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def get_download_path(job_id: int, user_id: int | None, token: str) -> str | None:
    db = SessionLocal()
    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if not job or job.status != "COMPLETED":
            return None
        if job.expires_at and job.expires_at < datetime.utcnow():
            return None
        meta = json.loads(job.metadata_json or "{}")
        if meta.get("download_token") != token:
            return None
        if job.user_id and user_id and job.user_id != user_id:
            return None
        return job.file_path if job.file_path and os.path.exists(job.file_path) else None
    finally:
        db.close()


def list_export_jobs(user_id: int | None = None, limit: int = 20) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(ExportJob).order_by(ExportJob.created_at.desc())
        if user_id:
            q = q.filter(ExportJob.user_id == user_id)
        return [
            {
                "id": r.id,
                "export_type": r.export_type,
                "scope": r.scope,
                "status": r.status,
                "file_url": r.file_url,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in q.limit(limit).all()
        ]
    finally:
        db.close()
