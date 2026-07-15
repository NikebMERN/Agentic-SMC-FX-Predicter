"""Shared Telegram HTTP settings (timeouts, proxy) for bot + notifier."""
from __future__ import annotations

import os

from utils.config import TELEGRAM_BOT_TOKEN

TELEGRAM_PROXY_URL = (os.getenv("TELEGRAM_PROXY_URL") or "").strip() or None
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))
TELEGRAM_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_WRITE_TIMEOUT", "30"))
TELEGRAM_POOL_TIMEOUT = float(os.getenv("TELEGRAM_POOL_TIMEOUT", "30"))
TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT = float(
    os.getenv("TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT", str(TELEGRAM_CONNECT_TIMEOUT))
)
TELEGRAM_GET_UPDATES_READ_TIMEOUT = float(
    os.getenv("TELEGRAM_GET_UPDATES_READ_TIMEOUT", "60")
)


def build_httpx_request_for_updates():
    """HTTPXRequest for long-polling getUpdates (longer read timeout)."""
    from telegram.request import HTTPXRequest

    kwargs = {
        "connect_timeout": TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT,
        "read_timeout": TELEGRAM_GET_UPDATES_READ_TIMEOUT,
        "write_timeout": TELEGRAM_WRITE_TIMEOUT,
        "pool_timeout": TELEGRAM_POOL_TIMEOUT,
    }
    if TELEGRAM_PROXY_URL:
        kwargs["proxy_url"] = TELEGRAM_PROXY_URL
    return HTTPXRequest(**kwargs)


def build_httpx_request():
    """HTTPXRequest for python-telegram-bot Application."""
    from telegram.request import HTTPXRequest

    kwargs = {
        "connect_timeout": TELEGRAM_CONNECT_TIMEOUT,
        "read_timeout": TELEGRAM_READ_TIMEOUT,
        "write_timeout": TELEGRAM_WRITE_TIMEOUT,
        "pool_timeout": TELEGRAM_POOL_TIMEOUT,
    }
    if TELEGRAM_PROXY_URL:
        kwargs["proxy_url"] = TELEGRAM_PROXY_URL
    return HTTPXRequest(**kwargs)


def requests_proxies() -> dict | None:
    if not TELEGRAM_PROXY_URL:
        return None
    return {"http": TELEGRAM_PROXY_URL, "https": TELEGRAM_PROXY_URL}


def requests_timeout() -> tuple[float, float]:
    return TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT


def api_base() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""


def redact(text) -> str:
    """Strip the bot token from any string destined for the logs.

    Exception messages from requests/httpx embed the full request URL,
    which contains the token — never write that to disk."""
    s = str(text)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in s:
        s = s.replace(TELEGRAM_BOT_TOKEN, "***TOKEN***")
    return s


def is_telegram_network_error(exc: BaseException | None) -> bool:
    """True for timeouts / connection failures to api.telegram.org."""
    if exc is None:
        return False
    try:
        from telegram.error import NetworkError, TimedOut
        if isinstance(exc, (NetworkError, TimedOut)):
            return True
    except ImportError:
        pass
    name = exc.__class__.__name__
    if name in ("ConnectError", "ConnectTimeout", "ReadTimeout", "NetworkError", "TimeoutException"):
        return True
    msg = str(exc).lower()
    if "connection attempts failed" in msg or "connect timeout" in msg:
        return True
    return is_telegram_network_error(getattr(exc, "__cause__", None))


def telegram_api_status() -> tuple[bool, str]:
    """Quick probe before starting long-polling, with redacted diagnostics."""
    if not TELEGRAM_BOT_TOKEN:
        return False, "TELEGRAM_BOT_TOKEN is missing"
    try:
        import requests

        r = requests.get(
            f"{api_base()}/getMe",
            timeout=(min(TELEGRAM_CONNECT_TIMEOUT, 8), min(TELEGRAM_READ_TIMEOUT, 12)),
            proxies=requests_proxies(),
        )
        if r.ok:
            return True, "ok"
        return False, f"Telegram getMe failed with HTTP {r.status_code}: {redact(r.text[:200])}"
    except Exception as exc:
        return False, redact(exc)


def telegram_api_reachable() -> bool:
    """Quick boolean probe before starting long-polling."""
    ok, _ = telegram_api_status()
    return ok


def bot_enabled() -> bool:
    raw = (os.getenv("TELEGRAM_BOT_ENABLED") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}
