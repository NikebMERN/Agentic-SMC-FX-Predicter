# utils/config.py
"""All runtime configuration, driven by environment variables.

Nothing in this file is ever rewritten at runtime — the symbol being
predicted is a function parameter throughout the engine.
"""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv  # type: ignore

from utils.pairs import DEFAULT_FX_PAIRS, pairs_from_env


def _normalize_aiven_mysql_host(parsed):
    host = parsed.hostname or ""
    if not parsed.scheme.startswith("mysql"):
        return parsed
    if not host.endswith(".aivencloud.com") or host.startswith("mysql-"):
        return parsed

    userinfo, separator, _hostport = parsed.netloc.rpartition("@")
    prefix = f"{userinfo}{separator}" if separator else ""
    port = f":{parsed.port}" if parsed.port else ""
    return parsed._replace(netloc=f"{prefix}mysql-{host}{port}")


def _normalize_database_url(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return url, None
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    parsed = urlsplit(url)
    parsed = _normalize_aiven_mysql_host(parsed)
    ssl_mode = None
    query_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower().replace("_", "-") == "ssl-mode":
            ssl_mode = value.strip().lower() or None
            continue
        query_params.append((key, value))
    normalized_url = urlunsplit(parsed._replace(query=urlencode(query_params)))
    return normalized_url, ssl_mode


# Load environment variables from .env
load_dotenv()

# 'production' (default) or 'development'. Development relaxes a few
# behaviours (e.g. password-reset codes are returned in the API response
# when SMTP is not configured, so the flow can be tested locally).
_raw_app_env = os.getenv("APP_ENV", "production").strip().lower()
if _raw_app_env in {"dev", "develop", "development"}:
    APP_ENV = "development"
else:
    APP_ENV = "production"
IS_DEVELOPMENT = APP_ENV == "development"

# -----------------------------
# External API Configuration
# -----------------------------
ALPHA_VANTAGE_API_KEY = (os.getenv("ALPHA_VANTAGE_API_KEY") or "").strip() or None

# OANDA v20 (preferred provider): free practice account works for data.
# OANDA_ENV: "practice" (api-fxpractice) or "live" (api-fxtrade).
OANDA_API_KEY = (os.getenv("OANDA_API_KEY") or "").strip() or None
OANDA_ENV = os.getenv("OANDA_ENV", "practice").lower()

# Which provider to use: "auto" tries OANDA first, then Alpha Vantage,
# then the cached CSV. "oanda" / "alphavantage" pin one provider.
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "auto").lower()
ALLOW_CACHE_ONLY_PRODUCTION = (
    os.getenv("ALLOW_CACHE_ONLY_PRODUCTION", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)

# All candle timestamps are normalised to this clock (the ICT/kill-zone
# convention is New York time; Alpha Vantage already ships US/Eastern,
# OANDA ships UTC and gets converted).
DATA_TZ = os.getenv("DATA_TZ", "America/New_York")

INTERVAL = os.getenv("DATA_INTERVAL", "60min")

# Skip live re-fetch when the pair's CSV is younger than this — protects
# the provider quota when several predictions arrive close together.
FETCH_COOLDOWN_MINUTES = int(os.getenv("FETCH_COOLDOWN_MINUTES", "5"))

# Pairs offered in the bot / CLI menus. Defaults to the full OANDA-style list
# in utils/pairs.py; override with SUPPORTED_PAIRS in .env if needed.
SUPPORTED_PAIRS = pairs_from_env(os.getenv("SUPPORTED_PAIRS")) or list(DEFAULT_FX_PAIRS)

# Kept for backward compatibility with older scripts.
SYMBOL = SUPPORTED_PAIRS[0] if SUPPORTED_PAIRS else "EURUSD"

# -----------------------------
# API server
# -----------------------------
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5000"))

# Comma-separated origin whitelist for CORS. "*" allows everything —
# fine for development, set your real frontend origin(s) in production.
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]
RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

# -----------------------------
# Admin bootstrap
# -----------------------------
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")

# -----------------------------
# Database Configuration
# -----------------------------
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DB", "smc_trader")

# DATABASE_URL overrides the MySQL pieces entirely (e.g. sqlite:///./smc.db
# for local development or testing without a MySQL server).
# When neither DATABASE_URL nor any MYSQL_* variable is set, fall back to a
# local SQLite file so the app works out of the box.
_MYSQL_CONFIGURED = any(
    os.getenv(k)
    for k in ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_DB")
)
DATABASE_URL, DATABASE_SSL_MODE = _normalize_database_url(os.getenv("DATABASE_URL"))
if not DATABASE_URL:
    if _MYSQL_CONFIGURED:
        # Credentials must be URL-encoded (passwords often contain /, @, ! ...).
        from urllib.parse import quote_plus
        _user = quote_plus(DB_USER)
        if DB_PASSWORD:
            DATABASE_URL = (
                f"mysql+pymysql://{_user}:{quote_plus(DB_PASSWORD)}"
                f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            )
        else:
            DATABASE_URL = f"mysql+pymysql://{_user}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        DATABASE_URL = "sqlite:///./smc.db"
        DATABASE_SSL_MODE = None

# -----------------------------
# Telegram Configuration
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Optional: TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080 (see utils/telegram_http.py)

# -----------------------------
# Local Data Folder
# -----------------------------
DATA_FOLDER = os.path.join(os.getcwd(), "data")  # points to ./data folder

# -----------------------------
# Live market stream relay
# -----------------------------
MARKET_STREAMS_ENABLED = (
    os.getenv("MARKET_STREAMS_ENABLED", "true").strip().lower()
    not in {"0", "false", "no", "off"}
)
MAX_MARKET_STREAMS = int(os.getenv("MAX_MARKET_STREAMS", "20"))
