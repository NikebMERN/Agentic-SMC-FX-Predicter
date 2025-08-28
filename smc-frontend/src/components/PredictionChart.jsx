// components/PredictionChart.jsx
import React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import "../css/PredictionChart.css";

const PredictionChart = ({ stopLoss, takeProfit }) => {
  let entry = (takeProfit + (2 * stopLoss)) / 3; // Example calculation for entry point

  const data = [
    { name: "Stop Loss", value: stopLoss },
    { name: "Entry", value: parseFloat(entry.toFixed(5)) },
    { name: "Take Profit", value: takeProfit },
  ];

  return (
    <div className="chart-container">
      <LineChart width={350} height={220} data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis domain={['auto', 'auto']} />
        <Tooltip />
        <Line type="monotone" dataKey="value" stroke="#00f" strokeWidth={2} />
      </LineChart>
    </div>
  );
};

export default PredictionChart;
