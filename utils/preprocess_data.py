import pandas as pd # type: ignore

def preprocess_data(path):
    df = pd.read_csv(path)

    # Rename 'Unnamed: 0' to 'Timestamp'
    df.rename(columns={
        "Unnamed: 0": "Timestamp",
        "1. open": "Open",
        "2. high": "High",
        "3. low": "Low",
        "4. close": "Close",
        "5. volume": "Volume"
    }, inplace=True)

    # Convert Timestamp to datetime
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df.set_index('Timestamp', inplace=True)

    # Convert prices and volume to numeric
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with missing values
    df.dropna(inplace=True)

    # Sort data by time (ascending)
    df.sort_values("Timestamp", inplace=True)

    return df
