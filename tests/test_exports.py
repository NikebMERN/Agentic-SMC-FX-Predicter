"""Tests for export jobs."""
from services.export_service import create_export_job, list_export_jobs


def test_export_job_create(initialized_db):
    from db.models import User
    from db.session import SessionLocal
    import time
    db = SessionLocal()
    user = db.query(User).filter(User.role == "admin").first()
    uid = user.id
    db.close()

    job = create_export_job(user_id=uid, export_type="CSV")
    assert job is not None
    time.sleep(0.5)
    jobs = list_export_jobs(user_id=uid)
    assert any(j["id"] == job.id for j in jobs)
