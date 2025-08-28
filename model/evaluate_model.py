import pandas as pd # type: ignore
import joblib # type: ignore
from sklearn.metrics import classification_report # type: ignore
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load the processed data and model
df = pd.read_csv("data/processed_features/all_features.csv")
model = joblib.load("model/model.joblib")
le = joblib.load("model/label_encoder.joblib")

# Prepare the data (drop unused columns)
df = df.drop(columns=["sma_trend", "smc_trend", "file"], errors='ignore')
df["combined_trend_encoded"] = le.transform(df["combined_trend"])

X = df.drop(columns=["combined_trend", "combined_trend_encoded"])
y = df["combined_trend_encoded"]

# Predict and evaluate
y_pred = model.predict(X)

print("=== Model Evaluation ===")
print("📊 Classification Report:")
print(classification_report(y, y_pred, target_names=le.classes_, zero_division=0))
print("✅ Evaluation completed successfully.")