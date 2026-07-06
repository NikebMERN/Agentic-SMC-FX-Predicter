# services/health_monitor.py
"""Track repeated failures and alert operators."""
import threading
import time

from utils.config import ADMIN_EMAIL
from utils.logger import get_logger
from utils.mailer import is_configured, send_email

log = get_logger("services.health_monitor")

THRESHOLD = int(__import__("os").getenv("ALERT_FAILURE_THRESHOLD", "3"))
INTERVAL_SEC = int(__import__("os").getenv("HEALTH_MONITOR_INTERVAL_SEC", "120"))

_counters: dict[str, int] = {"fetch": 0, "bot": 0}
_alerted: set[str] = set()
_running = False


def record_failure(kind: str, detail: str = ""):
    _counters[kind] = _counters.get(kind, 0) + 1
    log.warning("Health failure [%s] count=%s %s", kind, _counters[kind], detail)
    if _counters[kind] >= THRESHOLD and kind not in _alerted:
        _send_alert(kind, detail)
        _alerted.add(kind)


def record_success(kind: str):
    _counters[kind] = 0
    _alerted.discard(kind)


def _send_alert(kind: str, detail: str):
    msg = f"SmartFlow AI alert: repeated {kind} failures ({_counters[kind]}x). {detail}"
    log.error(msg)
    if is_configured() and ADMIN_EMAIL:
        send_email(ADMIN_EMAIL, "SmartFlow AI Alert", msg)
    try:
        from services.notifier import notify_admin
        notify_admin(msg)
    except Exception:
        pass


def _loop():
    global _running
    while _running:
        try:
            from utils.config import TELEGRAM_BOT_TOKEN
            from utils.telegram_http import bot_enabled, api_base, requests_proxies, requests_timeout
            if TELEGRAM_BOT_TOKEN and bot_enabled():
                import requests
                from utils.telegram_http import api_base, requests_proxies, requests_timeout

                r = requests.get(
                    f"{api_base()}/getMe",
                    timeout=requests_timeout(),
                    proxies=requests_proxies(),
                )
                if r.ok:
                    record_success("bot")
                else:
                    record_failure("bot", f"HTTP {r.status_code}")
        except Exception as exc:
            msg = str(exc)
            if "telegram.org" in msg or "Timed out" in msg or "timeout" in msg.lower():
                record_failure("bot", "Telegram API unreachable (timeout)")
            else:
                record_failure("bot", msg[:200])
        time.sleep(INTERVAL_SEC)


def start_health_monitor():
    global _running
    if _running:
        return
    _running = True
    threading.Thread(target=_loop, daemon=True, name="health-monitor").start()
    log.info("Health monitor started")
