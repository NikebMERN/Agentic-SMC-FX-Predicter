import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const TABS = [
  ["overview", "Overview"],
  ["models", "Models"],
  ["training", "Training Runs"],
  ["backtests", "Backtests"],
  ["leaderboard", "Leaderboard"],
  ["settings", "Settings"],
];

export default function MLOpsPage() {
  const [tab, setTab] = useState("overview");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [versions, setVersions] = useState([]);
  const [runs, setRuns] = useState([]);
  const [backtests, setBacktests] = useState([]);
  const [pairs, setPairs] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [v, r, b, p] = await Promise.all([
        api("/ml/model-versions"),
        api("/ml/training-runs"),
        api("/ml/backtests"),
        api("/performance/pairs"),
      ]);
      setVersions(v.versions || []);
      setRuns(r.runs || []);
      setBacktests(b.backtests || []);
      setPairs(p.pairs || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function retrainNow() {
    setMessage("");
    try {
      const res = await api("/ml/retrain-now", { method: "POST", body: JSON.stringify({}) });
      setMessage(`Retrain ${res.status}: ${res.models_created || 0} model(s) created`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function activate(id) {
    try {
      await api(`/ml/model-versions/${id}/activate`, { method: "POST" });
      setMessage(`Activated model version ${id}`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const active = versions.filter((v) => v.status === "ACTIVE");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">ML Operations</h1>
          <p className="text-sm text-[#8b949e]">Meta-labeling models, nightly retrain, promotion gates</p>
        </div>
        <button
          type="button"
          onClick={retrainNow}
          className="rounded bg-[#238636] px-4 py-2 text-sm font-medium hover:bg-[#2ea043]"
        >
          Retrain now
        </button>
      </div>

      <PageAlerts error={error} message={message} onDismiss={() => { setError(""); setMessage(""); }} />

      <div className="flex gap-2 border-b border-[#30363d] pb-2">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded px-3 py-1 text-sm ${tab === id ? "bg-[#21262d] text-white" : "text-[#8b949e]"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-[#8b949e]">Loading…</p>}

      {tab === "overview" && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-xs text-[#8b949e]">Active models</div>
            <div className="text-2xl font-semibold">{active.length}</div>
          </div>
          <div className="rounded border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-xs text-[#8b949e]">Last training run</div>
            <div className="text-sm">{runs[0]?.status || "—"}</div>
          </div>
          <div className="rounded border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-xs text-[#8b949e]">Compliance</div>
            <div className="text-sm">No auto-execution · Educational signals only</div>
          </div>
        </div>
      )}

      {tab === "models" && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[#30363d] text-[#8b949e]">
              <th className="py-2">ID</th>
              <th>Pair</th>
              <th>Status</th>
              <th>F1</th>
              <th>Precision</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id} className="border-b border-[#21262d]">
                <td className="py-2">{v.id}</td>
                <td>{v.symbol} {v.interval}</td>
                <td>{v.status}</td>
                <td>{v.f1?.toFixed?.(3) ?? "—"}</td>
                <td>{v.precision?.toFixed?.(3) ?? "—"}</td>
                <td>
                  {v.status !== "ACTIVE" && (
                    <button type="button" className="text-[#2f81f7]" onClick={() => activate(v.id)}>
                      Activate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "training" && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[#30363d] text-[#8b949e]">
              <th className="py-2">ID</th>
              <th>Type</th>
              <th>Status</th>
              <th>Created</th>
              <th>Promoted</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-[#21262d]">
                <td className="py-2">{r.id}</td>
                <td>{r.run_type}</td>
                <td>{r.status}</td>
                <td>{r.started_at?.slice(0, 19) ?? "—"}</td>
                <td>{r.models_promoted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "backtests" && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[#30363d] text-[#8b949e]">
              <th className="py-2">ID</th>
              <th>Model</th>
              <th>Pair</th>
              <th>F1</th>
              <th>Gate</th>
            </tr>
          </thead>
          <tbody>
            {backtests.map((b) => (
              <tr key={b.id} className="border-b border-[#21262d]">
                <td className="py-2">{b.id}</td>
                <td>{b.model_version_id}</td>
                <td>{b.symbol}</td>
                <td>{b.f1?.toFixed?.(3) ?? "—"}</td>
                <td>{b.passed_promotion_gate ? "PASS" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "leaderboard" && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[#30363d] text-[#8b949e]">
              <th className="py-2">Pair</th>
              <th>TF</th>
              <th>Win rate</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((p) => (
              <tr key={p.id} className="border-b border-[#21262d]">
                <td className="py-2">{p.symbol}</td>
                <td>{p.interval}</td>
                <td>{p.win_rate != null ? `${(p.win_rate * 100).toFixed(1)}%` : "—"}</td>
                <td>{p.status_recommendation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "settings" && (
        <p className="text-sm text-[#8b949e]">
          Promotion gate, recency weights, and ML thresholds are managed under Settings → ML Platform keys
          (ml_mode, promotion_gate_json, ml_blend_rule_weight, etc.).
        </p>
      )}
    </div>
  );
}
