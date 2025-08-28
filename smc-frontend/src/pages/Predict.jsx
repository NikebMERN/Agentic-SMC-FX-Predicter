// pages/Predict.jsx
import React, { useEffect, useState } from "react";
import "../css/Predict.css";
import PredictionChart from "../components/PredictionChart";
import { fetchPrediction } from "../services/api";
import { useParams } from "react-router-dom";

const backgroundByPrediction = {
    "strong downtrend": "bg_bearish.jpg",
    "weak downtrend": "bg_bearish.jpg",
    "sideways": "bg_neutral.jpg",
    "conflict": "bg_neutral.jpg",
    "don't enter": "bg_neutral.jpg",
    "weak uptrend": "bg_bullish.jpg",
    "strong uptrend": "bg_bullish.jpg",
};

const Predict = () => {
    const [predict, setPredict] = useState([]);
    const { pair } = useParams();
    // console.log(pair);

    //? Fetch prediction data based on the pair
    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await fetchPrediction(pair);
                setPredict(response);
                // console.log(response)
                // console.log(predict);
            } catch (error) {
                console.error("Error fetching prediction data:", error);
            }
        };
        fetchData();
    }, []);
    if (!predict || !predict[0]) return <p>Loading...</p>;

    const { prediction, confidence, action, stop_loss, take_profit } = predict[0];
    const background = backgroundByPrediction[prediction.toLowerCase()] || "bg_neutral.jpg";

    const getPredictionColor = (prediction) => {
        if (prediction.toLowerCase() === "strong downtrend") return "RED text-red-700 font-bold";
        if (prediction.toLowerCase() === "weak downtrend") return "LIGHT-RED text-red-400";
        if (prediction.toLowerCase() === "strong uptrend") return "GREEN text-green-700 font-bold";
        if (prediction.toLowerCase() === "weak uptrend") return "LIGHT-GREEN text-green-400";
        return "BLACK text-gray-700"; // Default color for other predictions
    };

    //? Determine action color based on the action type
    //? Assuming action can be "buy", "sell", or other values
    let actionColor = "";
    if (action.toLowerCase() === "buy") {
        actionColor = "GREEN";
    } else if (action.toLowerCase() === "sell") {
        actionColor = "RED";
    } else if (action.toLowerCase() === "don't enter") {
        actionColor = "BLACK";
    }

    return (
        <div className="predict-page">
            <div
                className="predict-container"
                style={{ backgroundImage: `url(../assets/${background})` }}
            >
                <div className="overlay">
                    <div className="content p-4 text-white">
                        <h1 className="text-3xl font-bold mb-2">{pair}</h1>
                        <p className={`text-xl mb-2`}>
                            Prediction: <span className={`${getPredictionColor(prediction)}`}>{prediction}</span>
                        </p>

                        <div className="mb-4">
                            <h2 className="text-lg font-semibold">Confidence Scores</h2>
                            <ul className="ml-4 list-disc">
                                {Object.entries(confidence).map(([k, v]) => (
                                    <li key={k}>
                                        {k}: <span className="font-medium">{v}%</span>
                                    </li>
                                ))}
                            </ul>
                        </div>

                        <PredictionChart stopLoss={stop_loss} takeProfit={take_profit} />

                        <div className="mt-6">
                            <p className={`final-action font-bold`}>
                                Final Action: <span className={`${actionColor}`}>{action.toUpperCase()}</span>
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Predict;
