# db/init_db.py
import sys
import os

# Make sure parent folder is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from session import Base, engine
from models import User, Account, Trade, Signal, TelegramLink, EquitySnapshot  # <-- import the classes, not "models"

# Create all tables
Base.metadata.create_all(bind=engine)

print("✅ Database tables created successfully!")
