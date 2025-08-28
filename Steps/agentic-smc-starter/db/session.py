
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utils.orm_config import get_db_url, get_env

DB_URL = get_db_url()
ECHO = get_env('SQLALCHEMY_ECHO', '0') == '1'

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600, echo=ECHO)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
