import { Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Predict from './pages/Predict';
import NOTPage from './pages/404Page';

const fakePredictionData = [
  {
    action: "don't enter",
    confidence: {
      Conflict: 1.0,
      "Strong Downtrend": 64.0,
      "Strong Uptrend": 11.0,
      "Weak Downtrend": 10.0,
      "Weak Uptrend": 14.0,
    },
    prediction: "weak uptrend",
    stop_loss: 142.70033,
    take_profit: 145.79834,
  },
];

function App() {
  return (
    <>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/predict/:pair" element={<Predict data={fakePredictionData} pairName="EURUSD" />} />
      <Route path="*" element={<NOTPage />} />
    </Routes>
    {/* <Predict data={fakePredictionData} pairName="EURUSD" /> */}
    </>
  );
}

export default App;
