import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker, declarative_base # type: ignore
from utils.config import DATABASE_SSL_MODE, DATABASE_URL

# Base for models
Base = declarative_base()

# DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Engine (MySQL in production; sqlite supported for dev/tests via DATABASE_URL)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
if DATABASE_URL.startswith("mysql+pymysql://") and DATABASE_SSL_MODE:
    if DATABASE_SSL_MODE not in {"disabled", "disable", "false", "0"}:
        _connect_args["ssl"] = {"verify_mode": "none"}
_engine_options = {
    "echo": False,
    "pool_pre_ping": True,
    "connect_args": _connect_args,
}
if not DATABASE_URL.startswith("sqlite"):
    _engine_options.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
    })
engine = create_engine(DATABASE_URL, **_engine_options)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
)
