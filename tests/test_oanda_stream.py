"""Tests for OANDA stream mock quotes."""
from services.oanda_stream import get_latest_quote, subscribe


def test_oanda_stream_quote():
    subscribe("EURUSD", lambda _: None)
    import time
    time.sleep(0.1)
    q = get_latest_quote("EURUSD")
    # Mock stream may need a moment on slow CI; allow None only if thread not started
    if q is None:
        time.sleep(1.0)
        q = get_latest_quote("EURUSD")
    assert q is not None
    assert "mid" in q
