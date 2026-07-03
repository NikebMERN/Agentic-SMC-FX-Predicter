# tests/test_telegram_register.py
from services.telegram_link import get_or_register_telegram_user, get_user_by_chat


def test_telegram_start_registers_pending_user(initialized_db):
    user = get_or_register_telegram_user("999001", "testtrader", "Test")
    assert user.username
    assert user.status == "pending"
    assert user.email == "tg_999001@telegram.local"
    assert get_user_by_chat("999001").id == user.id

    again = get_or_register_telegram_user("999001", "other", "Other")
    assert again.id == user.id
