import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";

export default function AlertsPage() {
  const [rules, setRules] = useState([]);
  const [pairs, setPairs] = useState("EURUSD");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api("/alerts/rules");
      setRules(res.rules || []);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createRule() {
    try {
      await api("/alerts/rules", {
        method: "POST",
        body: JSON.stringify({
          pairs: pairs.split(",").map((p) => p.trim().toUpperCase()).filter(Boolean),
          min_confidence: 0.6,
          timeframes: ["60min"],
        }),
      });
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Telegram Alerts</h1>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="rounded border border-white/10 bg-black/30 p-4 space-y-3">
        <label className="block text-sm">Pairs (comma-separated)</label>
        <input
          className="w-full rounded border border-white/20 bg-black/50 px-3 py-2"
          value={pairs}
          onChange={(e) => setPairs(e.target.value)}
        />
        <button type="button" onClick={createRule} className="rounded bg-emerald-600 px-4 py-2 text-sm">
          Add rule
        </button>
      </div>
      <ul className="space-y-2">
        {rules.map((r) => (
          <li key={r.id} className="rounded border border-white/10 p-3 text-sm">
            {(r.pairs || []).join(", ")} · min conf {(r.min_confidence * 100).toFixed(0)}%
          </li>
        ))}
      </ul>
    </div>
  );
}
