"""Tests for alert rules CRUD."""
from services.alert_scanner import create_rule, delete_rule, list_rules


def test_alert_rule_crud(initialized_db):
    from db.models import User
    from db.session import SessionLocal
    db = SessionLocal()
    user = db.query(User).filter(User.role == "admin").first()
    uid = user.id
    db.close()

    row = create_rule(uid, {"pairs": ["EURUSD"], "telegram_chat_id": "123"})
    assert row is not None
    rules = list_rules(uid)
    assert len(rules) >= 1
    assert delete_rule(row.id, uid) is True
