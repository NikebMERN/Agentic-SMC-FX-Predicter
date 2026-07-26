# tests/test_production_warnings.py
import logging

import pytest


def test_log_production_warnings_lists_misconfigurations(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./prod_test.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "123")
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")
    monkeypatch.delenv("OANDA_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_CACHE_ONLY_PRODUCTION", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    import importlib
    import utils.config as cfg

    importlib.reload(cfg)
    monkeypatch.setattr(cfg, "OANDA_API_KEY", None)
    monkeypatch.setattr(cfg, "ALPHA_VANTAGE_API_KEY", None)
    monkeypatch.setattr(cfg, "ALLOW_CACHE_ONLY_PRODUCTION", False)
    monkeypatch.setattr("utils.mailer.is_configured", lambda: False)

    from run import production_config_issues

    text = "\n".join(production_config_issues())
    assert "CORS_ORIGINS" in text
    assert "SMTP" in text
    assert "SQLite" in text
    assert "ADMIN_PASSWORD" in text
    assert "RATELIMIT_STORAGE_URI" in text
    assert "No live data provider" in text


def test_assert_production_ready_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./prod_test.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "123")
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")
    monkeypatch.delenv("OANDA_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_CACHE_ONLY_PRODUCTION", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    import importlib
    import utils.config as cfg

    importlib.reload(cfg)

    from run import assert_production_ready

    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        assert_production_ready()


def test_log_production_warnings_skipped_in_development(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "development")
    import importlib
    import utils.config as cfg

    importlib.reload(cfg)

    from run import log_production_warnings

    with caplog.at_level(logging.WARNING, logger="smartflow.run"):
        log_production_warnings()

    assert "Production configuration warnings" not in caplog.text
