import os
import sys
import subprocess
import requests  # type: ignore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.config import TELEGRAM_BOT_TOKEN

# ==== TELEGRAM CONFIG ====
TELEGRAM_TOKEN = TELEGRAM_BOT_TOKEN

# Project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_latest_chat_id():
    """Fetch the latest active Telegram chat_id."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        res = requests.get(url).json()
        chat_ids = [
            update["message"]["chat"]["id"]
            for update in res.get("result", [])
            if "message" in update
        ]
        if chat_ids:
            return chat_ids[-1]
    except Exception as e:
        print(f"[ERROR] Failed to fetch chat_id: {e}")
    return None

def update_config(symbol: str):
    """Update only the SYMBOL variable in utils/config.py without overwriting the rest."""
    config_path = os.path.join(PROJECT_ROOT, "utils", "config.py")
    lines = []

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            lines = f.readlines()

    symbol_set = False
    with open(config_path, "w") as f:
        for line in lines:
            if line.strip().startswith("SYMBOL"):
                f.write(f'SYMBOL = "{symbol}"\n')
                symbol_set = True
            else:
                f.write(line)
        if not symbol_set:
            f.write(f'\nSYMBOL = "{symbol}"\n')

    print(f"[CONFIG] Updated SYMBOL in config.py -> {symbol}")

def run_script(script_path: str, step_name: str):
    """Run a Python script with real-time console output from project root."""
    abs_path = os.path.join(PROJECT_ROOT, script_path)
    print(f"\n[RUN] {step_name} ({script_path}) ...")
    try:
        process = subprocess.Popen(
            ["python", abs_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=PROJECT_ROOT
        )
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            print(f"[ERROR] {step_name} failed (exit code {process.returncode}).")
            return False
        print(f"[SUCCESS] {step_name} completed.")
        return True
    except Exception as e:
        print(f"[ERROR] {step_name} failed: {e}")
        return False

def run_fetch(symbol: str):
    """Run all required scripts for the given symbol."""
    # Ensure the data folder exists
    data_folder = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_folder, exist_ok=True)

    scripts = [
        ("Fetching market data", "utils/fetch_data.py"),
        ("Creating features", "features/create_features.py"),
        ("Training model", "model/train_model.py"),
        ("Evaluating model", "model/evaluate_model.py")
    ]

    for step_name, script_path in scripts:
        success = run_script(script_path, step_name)
        if not success:
            print(f"[FETCH] Stopped at {step_name} for {symbol}.")
            return False

    print(f"[FETCH] All steps completed for {symbol} successfully.")
    return True

def notify(symbol: str):
    """Send a Telegram notification to the latest active chat."""
    chat_id = get_latest_chat_id()
    if not chat_id:
        print("[WARN] No active chat_id found. Skipping notify.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    msg = f"✅ {symbol} CSV updated successfully."
    try:
        requests.post(url, data={"chat_id": chat_id, "text": msg})
        print(f"[NOTIFY] Sent Telegram alert for {symbol} to chat_id {chat_id}")
    except Exception as e:
        print(f"[ERROR] Telegram notify failed: {e}")

def fetch_single_symbol(symbol: str):
    """Fetch latest data and retrain model for a single currency pair."""
    print(f"\n=== Processing {symbol} ===")
    update_config(symbol)
    success = run_fetch(symbol)
    if success:
        notify(symbol)

# Example usage:
# if __name__ == "__main__":
#     fetch_single_symbol("EURUSD")
