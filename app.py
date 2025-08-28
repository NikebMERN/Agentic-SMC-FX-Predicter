from flask import Flask, request, jsonify
from flask_cors import CORS  # type: ignore
import os
import pandas as pd
from predict.predict_direction import predict_market_direction

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DATA_FOLDER = "data"


def decide_action(confidence_scores):
    """Determine trading action based on model's confidence scores."""
    if not confidence_scores:
        return "Don't Enter"

    top_label, top_prob = max(confidence_scores.items(), key=lambda x: x[1])
    label = top_label.lower()

    if label in ["strong uptrend", "buy"]:
        return "Buy"
    elif label in ["strong downtrend", "sell"]:
        return "Sell"
    else:
        return "Don't Enter"


# ✅ Calculate TP and SL in pips
def calculate_tp_sl(csv_file_path, action, sl_pips=10, risk_reward_ratio=2):
    """
    Calculate TP and SL using pip values with a risk-to-reward ratio.
    Default: SL = 10 pips, RRR = 2 (so TP = 20 pips).
    """
    df = pd.read_csv(csv_file_path)

    if df.empty or "Close" not in df.columns:
        return None, None

    last_close = df["Close"].iloc[-1]

    # Pip size detection (JPY pairs use 0.01, others use 0.0001)
    pip_size = 0.01 if "JPY" in csv_file_path.upper() else 0.0001

    # Compute pip distances
    tp_pips = sl_pips * risk_reward_ratio

    if action == "Buy":
        sl = last_close - (sl_pips * pip_size)
        tp = last_close + (tp_pips * pip_size)
    elif action == "Sell":
        sl = last_close + (sl_pips * pip_size)
        tp = last_close - (tp_pips * pip_size)
    else:
        return None, None

    return round(tp, 5), round(sl, 5)
# ❌ Original function without RRR    """
    # Calculate TP and SL using pip values.
    # Default: TP = 20 pips, SL = 10 pips.
    # """
    # df = pd.read_csv(csv_file_path)

    # if df.empty or "Close" not in df.columns:
    #     return None, None

    # last_close = df["Close"].iloc[-1]

    # # Pip size detection (JPY pairs use 0.01, others use 0.0001)
    # pip_size = 0.01 if "JPY" in csv_file_path.upper() else 0.0001

    # if action == "Buy":
    #     sl = last_close - (sl_pips * pip_size)
    #     tp = last_close + (tp_pips * pip_size)
    # elif action == "Sell":
    #     sl = last_close + (sl_pips * pip_size)
    #     tp = last_close - (tp_pips * pip_size)
    # else:
    #     return None, None

    # return round(tp, 5), round(sl, 5)


@app.route("/")
def index():
    return jsonify({
        "message": "Welcome to the SMC Forex Predictor API.",
        "endpoints": {
            "GET /data": "List available data files",
            "POST /predict": "Send filename to get market prediction"
        }
    })


@app.route("/data", methods=["GET"])
def list_data_files():
    try:
        files = [f for f in os.listdir(DATA_FOLDER) if f.endswith(".csv")]
        return jsonify({"available_files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        filename = data.get("filename")

        if not filename:
            return jsonify({"error": "Filename is required."}), 400

        filepath = os.path.join(DATA_FOLDER, filename)

        if not os.path.exists(filepath):
            return jsonify({"error": f"File '{filename}' not found."}), 404

        # Run prediction
        results = predict_market_direction(filepath)

        response = []
        for label, confidence_scores in results:
            action = decide_action(confidence_scores)
            tp, sl = calculate_tp_sl(filepath, action)

            response.append({
                "prediction": label,
                "confidence": {k: round(v * 100, 2) for k, v in confidence_scores.items()},
                "action": action,
                "take_profit": tp,
                "stop_loss": sl
            })

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
