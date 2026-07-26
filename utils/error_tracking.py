"""Optional production exception tracking."""
from __future__ import annotations

import os


def init_error_tracking() -> bool:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("APP_ENV", "development"),
            release=os.getenv("RENDER_GIT_COMMIT") or os.getenv("APP_RELEASE"),
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,
        )
        return True
    except Exception:
        return False
