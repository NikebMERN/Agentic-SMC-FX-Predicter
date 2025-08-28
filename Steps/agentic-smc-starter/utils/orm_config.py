
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=Path('.') / '.env')

def get_env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)

def get_db_url() -> str:
    url = os.getenv('MYSQL_URL')
    if url and url.strip():
        return url
    host = os.getenv('MYSQL_HOST', 'localhost')
    port = os.getenv('MYSQL_PORT', '3306')
    user = os.getenv('MYSQL_USER', 'root')
    password = os.getenv('MYSQL_PASSWORD', '')
    db = os.getenv('MYSQL_DB', 'smc_trader')
    # Using pymysql so we don't need C build tools
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"

def is_debug() -> bool:
    return os.getenv('APP_ENV', 'dev') in ('dev', 'debug')
