import requests # type: ignore
import pandas as pd # type: ignore
import os
from datetime import datetime
from config import ALPHA_VANTAGE_API_KEY, SYMBOL, INTERVAL

# Constants
BASE_URL = "https://www.alphavantage.co/query"
OUTPUT_FILE = f"data/{SYMBOL}_{INTERVAL}.csv"  # Save to root directory

def fetch_intraday_data(symbol=SYMBOL, interval=INTERVAL, api_key=ALPHA_VANTAGE_API_KEY):
    print(f"[INFO] Fetching intraday data for {symbol} @ {interval}...")

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "apikey": api_key,
        "datatype": "json",
        "outputsize": "full"
    }

    response = requests.get(BASE_URL, params=params)
    if response.status_code != 200:
        raise Exception(f"[ERROR] Failed to fetch data: {response.status_code}")

    data = response.json()

    key = f"Time Series ({interval})"
    if key not in data:
        raise Exception(f"[ERROR] Invalid response format. Available keys: {data.keys()}")

    df = pd.DataFrame.from_dict(data[key], orient="index")
    df = df.rename(columns={
        "1. open": "Open",
        "2. high": "High",
        "3. low": "Low",
        "4. close": "Close",
        "5. volume": "Volume"
    })

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.astype(float)

    return df

def save_data(df, file_path=OUTPUT_FILE):
    df.to_csv(file_path)
    print(f"[SUCCESS] Data saved to {file_path}")

if __name__ == "__main__":
    try:
        df = fetch_intraday_data()
        save_data(df)
    except Exception as e:
        print(f"[EXCEPTION] {e}")
