import os
import pandas as pd  # type: ignore
from sklearn.ensemble import RandomForestClassifier  # type: ignore
from sklearn.preprocessing import LabelEncoder  # type: ignore
import joblib  # type: ignore
from sklearn.metrics import classification_report  # type: ignore

# Ensure output folder exists
os.makedirs("model", exist_ok=True)

# Load the data
df = pd.read_csv("data/processed_features/all_features.csv")

# Drop unnecessary columns (keep all relevant features)
df = df.drop(columns=["sma_trend", "smc_trend", "file"], errors='ignore')

# Encode the target labels
le = LabelEncoder()
df["combined_trend_encoded"] = le.fit_transform(df["combined_trend"])

# Define X and y
X = df.drop(columns=["combined_trend", "combined_trend_encoded"])
y = df["combined_trend_encoded"]

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
model.fit(X, y)

# Save model and encoder
joblib.dump(model, "model/model.joblib")
joblib.dump(le, "model/label_encoder.joblib")

# Predict and report
y_pred = model.predict(X)
print("\n=== Model Training Complete ===")
print("Model trained using all features on full dataset with RandomForestClassifier.")
print("\n📊 Classification Report (on training data):")
print(classification_report(y, y_pred, target_names=le.classes_, zero_division=0))
print("✅ Model trained on full dataset and saved to 'model/model.joblib'")
print("🔖 Label encoder saved to 'model/label_encoder.joblib'")
print(f"🎯 Classes: {list(le.classes_)}")
