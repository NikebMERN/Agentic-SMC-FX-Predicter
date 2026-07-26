"""Immutable, versioned dataset manifests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from db.models import DatasetVersion, DatasetVersionRecord, TrainingRecord
from db.session import SessionLocal
from services.training_service import build_training_sample


def create_dataset_version(tier: str, *, created_by: int | None = None, parent_version_id: int | None = None):
    tier = tier.upper()
    if tier not in {"PENDING_REVIEW", "APPROVED", "REJECTED", "GOLD"}:
        raise ValueError("Invalid dataset tier")
    db = SessionLocal()
    try:
        accepted_tiers = ("APPROVED", "GOLD") if tier == "APPROVED" else (tier,)
        records = (
            db.query(TrainingRecord)
            .filter(
                TrainingRecord.dataset_tier.in_(accepted_tiers),
                TrainingRecord.suspicious.is_(False),
            )
            .order_by(TrainingRecord.id)
            .all()
        )
        manifest = []
        for record in records:
            sample = build_training_sample(record, record.prediction)
            payload = sample or {"record_id": record.id, "prediction_id": record.prediction_id}
            record_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            manifest.append({"training_record_id": record.id, "record_hash": record_hash})
        content_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        tag = f"{tier.lower()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{content_hash[:8]}"
        version = DatasetVersion(
            version_tag=tag, tier=tier, parent_version_id=parent_version_id,
            manifest_json=json.dumps(manifest), record_count=len(manifest),
            content_hash=content_hash, created_by=created_by,
        )
        db.add(version)
        db.flush()
        for item in manifest:
            db.add(DatasetVersionRecord(
                dataset_version_id=version.id,
                training_record_id=item["training_record_id"],
                record_hash=item["record_hash"],
            ))
        db.commit()
        db.refresh(version)
        return version
    finally:
        db.close()


def promote_dataset(version_id: int) -> bool:
    db = SessionLocal()
    try:
        row = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
        if not row:
            return False
        db.query(DatasetVersion).filter(
            DatasetVersion.tier == row.tier, DatasetVersion.status == "ACTIVE"
        ).update({"status": "ARCHIVED"}, synchronize_session=False)
        row.status = "ACTIVE"
        row.promoted_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()
