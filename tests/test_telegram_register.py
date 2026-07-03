# tests/test_telegram_register.py
from services.telegram_link import get_or_register_telegram_user, get_user_by_chat
from services.user_access import DEFAULT_SIGNALS_QUOTA


def test_telegram_start_registers_active_trial_user(initialized_db):
    """First /start auto-registers an ACTIVE account with the free trial
    quota — same policy as web registration."""
    user = get_or_register_telegram_user("999001", "testtrader", "Test")
    assert user.username
    assert user.status == "active"
    assert user.signals_remaining == DEFAULT_SIGNALS_QUOTA
    assert user.email == "tg_999001@telegram.local"
    assert get_user_by_chat("999001").id == user.id

    again = get_or_register_telegram_user("999001", "other", "Other")
    assert again.id == user.id
