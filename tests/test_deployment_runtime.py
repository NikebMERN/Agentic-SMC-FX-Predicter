from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _services():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    return {service["name"]: service for service in blueprint["services"]}


def test_render_separates_api_worker_scheduler_and_cache():
    services = _services()
    assert services["smartflow-api"]["type"] == "web"
    assert services["smartflow-worker"]["type"] == "worker"
    assert services["smartflow-scheduler"]["type"] == "worker"
    assert services["smartflow-telegram"]["type"] == "worker"
    assert services["smartflow-cache"]["type"] == "keyvalue"


def test_render_web_uses_readiness_and_production_wsgi():
    api = _services()["smartflow-api"]
    assert api["healthCheckPath"] == "/readyz"
    assert api["numInstances"] >= 2
    assert "gunicorn" in api["dockerCommand"]
    assert api["maxShutdownDelaySeconds"] >= 30


def test_render_workers_have_shutdown_window_and_redis():
    for name in ("smartflow-worker", "smartflow-scheduler", "smartflow-telegram"):
        service = _services()[name]
        assert service["maxShutdownDelaySeconds"] >= 60
        env = {item["key"]: item for item in service["envVars"]}
        assert env["DATABASE_URL"]["sync"] is False
        assert env["REDIS_URL"]["fromService"]["name"] == "smartflow-cache"
        assert env["LOG_FORMAT"]["value"] == "json"


def test_render_secrets_are_not_committed():
    for service in _services().values():
        for variable in service.get("envVars", []):
            if variable["key"] in {
                "DATABASE_URL",
                "SECRET_KEY",
                "ADMIN_PASSWORD",
                "TELEGRAM_BOT_TOKEN",
                "OANDA_API_KEY",
                "ALPHA_VANTAGE_API_KEY",
                "SENTRY_DSN",
            }:
                assert variable.get("sync") is False
