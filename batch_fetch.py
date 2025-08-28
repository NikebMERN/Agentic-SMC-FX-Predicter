# batch_fetch.py

import subprocess
import time

currency_pairs = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", 
    # "EURGBP", "EURJPY",
    # "GBPJPY", "EURCHF", "AUDJPY", "CHFJPY", "EURAUD", "AUDCAD", "CADJPY", "EURNZD", "GBPAUD",
    # "NZDJPY", "AUDNZD", "USDHKD", "USDSEK", "USDSGD", "USDZAR", "USDNOK", "EURCAD", "GBPCHF", 
    # "GBPCAD", "NZDCAD", "AUDCHF", "NZDCHF", "CADCHF", "SGDJPY", "USDTRY", "EURPLN", "EURTRY", 
    # "USDPLN", "USDTHB", "USDINR", "USDMXN", "USDCNH", "EURSEK", "EURNOK", "GBPZAR", "EURSGD",
    # "EURZAR", "EURHKD", "EURMXN", "EURHUF", "GBPNZD", "GBPHKD", "GBPSGD", "GBPSEK", "GBPNOK",
    # "GBPPLN", "AUDSGD", "HUFJPY", "AUDSEK", "AUDNOK", "AUDHKD", "AUDPLN", "CADSEK", "CADNOK",
    # "CADHKD", "CADHUF", "CHFSGD", "NZDHKD", "NZDSEK", "NZDNOK", "NZDSGD", "CHFSGD", "CHFNOK",
    # "CHFSEK", "CHFAUD", "CHFCAD", "CHFPLN", "SGDCAD", "SGDCHF", "SGDAUD", "SGDNZD", "NOKJPY", 
    # "SEKJPY", "TRYJPY", "ZARJPY", "PLNJPY", "MXNJPY", "THBJPY", "CNHJPY", "INRJPY", "HKDJPY",
    # "USDILS", "EURILS", "USDETB", "GBPILS", "AUDILS", "NZDILS", "CADILS", "CHFILS", "SGDILS",
    # "USDHUF", "EURHUF", "GBPHUF", "AUDHUF",
]

for symbol in currency_pairs:
    print(f"\n=== Fetching {symbol} ===")

    # Update config.py SYMBOL
    with open("utils/config.py", "r") as f:
        lines = f.readlines()

    with open("utils/config.py", "w") as f:
        for line in lines:
            if line.startswith("SYMBOL"):
                f.write(f'SYMBOL = "{symbol}"\n')
            else:
                f.write(line)

    # Run the fetch_data script
    try:
        subprocess.run(["python", "utils/fetch_data.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Fetch failed for {symbol}: {e}")

    # Optional: wait to avoid API rate limits
    time.sleep(15)  # Alpha Vantage free tier has 5 calls/min limit
