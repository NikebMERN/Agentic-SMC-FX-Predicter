# utils/logger.py
"""Central logging for the whole application.

Every module gets its logger via get_logger(__name__). Logs go to the
console and to a rotating file under logs/smartflow.log so production
issues can be diagnosed after the fact.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.path.join(LOG_DIR, "smartflow.log")

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def _configure_root():
    global _configured
    if _configured:
        return

    root = logging.getLogger("smartflow")
    root.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

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
