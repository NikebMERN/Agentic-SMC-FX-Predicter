# services/admin_audit.py
"""Persist admin actions to the admin_logs table."""
import json

from db.models import AdminLog
from db.session import SessionLocal
from flask import request  # type: ignore
from utils.logger import get_logger

log = get_logger("admin.audit")


def log_admin_action(
    admin_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
):
    ip = request.remote_addr if request else None
    db = SessionLocal()
    try:
        db.add(AdminLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail_json=json.dumps(detail or {}),
            ip=ip,
        ))
        db.commit()
    except Exception:
        log.exception("Failed to write admin audit log")
        db.rollback()
    finally:
        db.close()
    log.info("Admin %s: %s %s %s", admin_id, action, target_type, target_id)
