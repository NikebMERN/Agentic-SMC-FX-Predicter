import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker, declarative_base # type: ignore
from utils.config import DATABASE_URL

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
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
