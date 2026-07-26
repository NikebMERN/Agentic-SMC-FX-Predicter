# tests/test_app_env.py
import importlib

import pytest

from tests.helpers import register_and_login


@pytest.mark.parametrize("raw_env", ["dev", "develop", "development"])
def test_app_env_aliases_normalize_to_development(monkeypatch, raw_env):
    monkeypatch.setenv("APP_ENV", raw_env)
    import utils.config as cfg

    importlib.reload(cfg)
    assert cfg.APP_ENV == "development"
    assert cfg.IS_DEVELOPMENT is True


def test_app_env_production_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    import utils.config as cfg

    importlib.reload(cfg)
    assert cfg.APP_ENV == "production"
    assert cfg.IS_DEVELOPMENT is False


@pytest.mark.parametrize("raw_env", ["dev", "development"])
def test_forgot_password_returns_dev_code_in_development(
    client, admin_token, monkeypatch, raw_env
):
    monkeypatch.setenv("APP_ENV", raw_env)
    import utils.config as cfg

    importlib.reload(cfg)
    import app as app_module

    importlib.reload(app_module)
    monkeypatch.setattr("services.user_service.mailer.send_email", lambda *args, **kwargs: False)

    user = register_and_login(
        client,
        admin_token,
        username="resetuser",
        email="reset@test.local",
        password="SecurePass123!",
    )
    res = client.post("/forgot-password", json={"email": user["email"]})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert "dev_code" in body
    assert body["dev_code"]
