# utils/logger.py
"""Central logging for the whole application.

Every module gets its logger via get_logger(__name__). Logs go to the
console and to a rotating file under logs/smartflow.log so production
issues can be diagnosed after the fact.
"""
import logging
import json
import os
from logging.handlers import RotatingFileHandler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.path.join(LOG_DIR, "smartflow.log")

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": os.getenv("SERVICE_ROLE", "unknown"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure_root():
    global _configured
    if _configured:
        return

    root = logging.getLogger("smartflow")
    root.setLevel(LOG_LEVEL)
    formatter = (
        JsonFormatter()
        if os.getenv("LOG_FORMAT", "text").lower() == "json"
        else logging.Formatter(_FORMAT)
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if os.getenv("LOG_TO_FILE", "true").lower() in {"1", "true", "yes", "on"}:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the shared 'smartflow' root."""
    _configure_root()
    return logging.getLogger(f"smartflow.{name}")
