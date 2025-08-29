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
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DB", "smc_trader")  # or your actual DB

if DB_PASSWORD:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# -----------------------------
# Telegram Configuration
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# -----------------------------
# Local Data Folder
# -----------------------------
DATA_FOLDER = os.path.join(os.getcwd(), "data")  # points to ./data folder
