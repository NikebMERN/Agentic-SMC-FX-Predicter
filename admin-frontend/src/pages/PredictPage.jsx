import { useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const INTERVALS = ["5min", "15min", "30min", "60min"];
const STRATEGIES = [
  { value: "both", label: "SMC + ICT (combined)" },
  { value: "smc", label: "SMC only" },
  { value: "ict", label: "ICT only" },
];

export default function PredictPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [candleInterval, setCandleInterval] = useState("60min");
  const [pullLatest, setPullLatest] = useState(true);
  const [strategy, setStrategy] = useState("both");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function run() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await api("/predict", {
        method: "POST",
        body: JSON.stringify({ symbol, interval: candleInterval, fetch: pullLatest, strategy }),
      });
      setResult(r);
    } catch (e) {
      setError(e.message || "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  const d = result?.decision;

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Run a prediction</h1>
      <PageAlerts error={error} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} className="w-28 rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
        <select value={candleInterval} onChange={(e) => setCandleInterval(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          {INTERVALS.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
        <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          {STRATEGIES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={pullLatest} onChange={(e) => setPullLatest(e.target.checked)} /> pull latest data
        </label>
        <button type="button" onClick={run} disabled={loading} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white disabled:opacity-50">{loading ? "Working…" : "Predict"}</button>
      </div>
      {d && (
        <div className="mb-4 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <p className="text-lg">
            {result.symbol} → <strong className={d.action === "BUY" ? "text-[#3fb950]" : d.action === "SELL" ? "text-[#f85149]" : "text-[#d29922]"}>{d.action}</strong>
            {" "}(confidence {(d.confidence * 100).toFixed(0)}%)
          </p>
          {result.strategy && (
            <p className="text-sm text-[#8b949e]">Mode: {STRATEGIES.find((s) => s.value === result.strategy)?.label || result.strategy}</p>
          )}
          {d.entry && <p className="text-sm text-[#8b949e]">Entry {d.entry} · SL {d.stop_loss} · TP {d.take_profit} · RR {d.risk_reward}</p>}
          <ul className="mt-3 space-y-1 text-sm text-[#8b949e]">{d.reasoning?.map((r, i) => <li key={i}>• {r}</li>)}</ul>
          {d.vetoes?.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-[#f85149]">{d.vetoes.map((v, i) => <li key={i}>• {v}</li>)}</ul>
          )}
        </div>
      )}
      {result && <pre className="max-h-96 overflow-auto rounded border border-[#30363d] bg-[#0d1117] p-3 text-xs">{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}
