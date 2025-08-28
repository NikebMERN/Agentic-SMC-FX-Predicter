import joblib  # type: ignore
import pandas as pd  # type: ignore
import sys
import os

# Allow relative imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from features.create_features import extract_features

def predict_market_direction(file_path):
    # Load the trained model and label encoder
    model = joblib.load("model/model.joblib")
    label_encoder = joblib.load("model/label_encoder.joblib")

    # Extract features from the input CSV file
    features_df = extract_features(file_path)

    # Drop non-numeric columns that the model doesn't need
    X = features_df.drop(columns=["sma_trend", "smc_trend", "combined_trend"], errors="ignore")

    # Predict encoded class labels
    predictions_encoded = model.predict(X)

    # Decode predicted class labels to original strings
    predictions = label_encoder.inverse_transform(predictions_encoded)

    # Predict class probabilities for confidence scores
    probs = model.predict_proba(X)

    # Get class names by decoding model.classes_
    class_names = label_encoder.inverse_transform(model.classes_)

    results = []
    for i in range(len(predictions)):
        # Map class names to their probabilities
        prob_dict = {class_names[j]: probs[i][j] for j in range(len(class_names))}
        results.append((predictions[i], prob_dict))

    return results
