# tests/conftest.py
"""Test environment: sqlite database, fixed secrets, no live fetching.

Environment must be set BEFORE any project module is imported, because
config/session build the engine at import time. load_dotenv() does not
override pre-set variables, so these values win over any local .env.
"""
import os
import sys

# Per-process db file so concurrent pytest runs (or an open editor test
# runner) can never lock each other out on Windows.
_TEST_DB = f"test_smc_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{_TEST_DB}"
os.environ["APP_ENV"] = "development"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
os.environ["ALPHA_VANTAGE_API_KEY"] = ""      # tests never fetch live data
os.environ["OANDA_API_KEY"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["FETCH_COOLDOWN_MINUTES"] = "0"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def synthetic_ohlc() -> pd.DataFrame:
    """A 600-candle random walk with realistic hourly timestamps."""
    rng = np.random.default_rng(7)
    n = 600
    idx = pd.date_range("2025-01-06 00:00", periods=n, freq="h")
    close = 1.10 + np.cumsum(rng.normal(0, 0.0012, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = np.abs(rng.normal(0, 0.0008, n)) + 0.0002
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 0.0},
        index=pd.Index(idx, name="Timestamp"),
    )


@pytest.fixture(scope="session")
def synthetic_csv(synthetic_ohlc, tmp_path_factory) -> str:
    """Synthetic pair CSV placed in the real data dir (cleaned afterwards)."""
    from engine.data import DATA_DIR
    path = os.path.join(DATA_DIR, "TSTUSD_60min.csv")
    synthetic_ohlc.to_csv(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope="session")
def initialized_db():
    """Fresh sqlite schema + bootstrapped admin for API tests."""
    if os.path.exists(_TEST_DB):
        try:
            os.remove(_TEST_DB)
        except PermissionError:
            pass
    from run import init_database
    assert init_database() is True
    yield
    from db.session import engine
    engine.dispose()
    try:
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
    except PermissionError:
        pass  # leftover handle on Windows — the per-pid name keeps runs isolated


@pytest.fixture()
def client(initialized_db):
    from app import app, limiter
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    limiter.enabled = False
    with app.test_client() as c:
        yield c



@pytest.fixture()
def admin_token(client) -> str:
    res = client.post(
        "/admin/api/login",
        json={"email": "admin@test.local", "password": "test-admin-pass"},
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["token"]
