# utils/config.py

import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# -----------------------------
# External API Configuration
# -----------------------------
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
SYMBOL = "NZDUSD"
INTERVAL = "5min"

# -----------------------------
# Database Configuration
# -----------------------------
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "smc_trader")

# DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# -----------------------------
# Telegram Configuration
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
