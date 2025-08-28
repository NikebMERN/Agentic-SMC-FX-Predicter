# config.py

import os
from dotenv import load_dotenv  # type: ignore

load_dotenv()
# Alpha Vantage Configuration
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

# You can also define symbol, interval, etc. if you want
SYMBOL = "NZDUSD"
INTERVAL = "5min"
