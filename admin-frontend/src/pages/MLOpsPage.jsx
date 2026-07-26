import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const TABS = ["overview", "models", "training", "backtests", "datasets", "promotions"];
const metric = (value, digits = 3) => value == null ? "—" : Number(value).toFixed(digits);

export default function MLOpsPage() {
  const [tab, setTab] = useState("overview");
  const [data, setData] = useState({ versions: [], runs: [], backtests: [], monitoring: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [versions, runs, backtests, monitoring] = await Promise.all([
        api("/ml/model-versions"), api("/ml/training-runs"),
        api("/ml/backtests"), api("/ml/monitoring"),
      ]);
      setData({
        versions: versions.versions || [],
        runs: runs.runs || [],
        backtests: backtests.backtests || [],
        monitoring,
      });
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function activate(id) {
    if (!window.confirm(`Activate model version ${id}?`)) return;
    try {
      await api(`/ml/model-versions/${id}/activate`, { method: "POST" });
      setNotice(`Model ${id} activated. Previous active version remains available for rollback.`);
      load();
    } catch (e) { setError(e.message); }
  }

  async function retrain() {
    try {
      const result = await api("/ml/retrain-now", { method: "POST", body: "{}" });
      setNotice(`Retraining ${result.status}: ${result.models_created || 0} candidates created`);
      load();
    } catch (e) { setError(e.message); }
  }

  const monitoring = data.monitoring || {};
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">ML Monitoring</h1>
          <p className="text-sm text-[#8b949e]">Datasets, training, shadow evaluation, promotion, and economic performance.</p>
        </div>
        <button type="button" onClick={retrain} className="rounded bg-[#238636] px-4 py-2 text-sm text-white">Retrain now</button>
      </div>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="flex flex-wrap gap-2 border-b border-[#30363d] pb-2">
        {TABS.map((name) => (
          <button key={name} type="button" onClick={() => setTab(name)}
            className={`rounded px-3 py-1 text-sm capitalize ${tab === name ? "bg-[#21262d]" : "text-[#8b949e]"}`}>
            {name}
          </button>
        ))}
      </div>
      {loading && <p className="text-sm text-[#8b949e]">Loading…</p>}

      {tab === "overview" && (
        <div className="grid gap-3 md:grid-cols-4">
          {[
            ["Dataset size", monitoring.dataset_size || 0],
            ["Feedback", monitoring.feedback_total || 0],
            ["Active models", data.versions.filter((item) => item.status === "ACTIVE").length],
            ["Training runs", data.runs.length],
            ...Object.entries(monitoring.tiers || {}).map(([key, value]) => [key.replaceAll("_", " "), value]),
          ].map(([label, value]) => (
            <div key={label} className="rounded border border-[#30363d] bg-[#161b22] p-4">
              <div className="text-2xl font-semibold">{value}</div>
              <div className="text-xs text-[#8b949e]">{label}</div>
            </div>
          ))}
        </div>
      )}

      {tab === "models" && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[#8b949e]"><tr><th className="pb-2">ID</th><th>Market</th><th>Status</th><th>Precision</th><th>Recall</th><th>F1</th><th>PF</th><th>Expectancy</th><th>Sharpe</th><th>Max DD</th><th /></tr></thead>
            <tbody>{data.versions.map((row) => (
              <tr key={row.id} className="border-t border-[#30363d]">
                <td className="py-2">{row.id}</td><td>{row.symbol} · {row.interval} · {row.trading_style}</td><td>{row.status}</td>
                <td>{metric(row.precision)}</td><td>{metric(row.recall)}</td><td>{metric(row.f1)}</td>
                <td>{metric(row.metrics?.profit_factor, 2)}</td><td>{metric(row.metrics?.expectancy)}</td>
                <td>{metric(row.metrics?.sharpe_ratio, 2)}</td><td>{metric(row.metrics?.max_drawdown, 2)}</td>
                <td>{row.status !== "ACTIVE" && <button type="button" onClick={() => activate(row.id)} className="text-[#2f81f7]">Activate / rollback</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab === "training" && (
        <table className="w-full text-left text-sm">
          <thead className="text-[#8b949e]"><tr><th className="pb-2">ID</th><th>Type</th><th>Status</th><th>Pairs</th><th>Created</th><th>Promoted</th><th>Error</th></tr></thead>
          <tbody>{data.runs.map((row) => (
            <tr key={row.id} className="border-t border-[#30363d]"><td className="py-2">{row.id}</td><td>{row.run_type}</td><td>{row.status}</td><td>{row.pairs_processed}</td><td>{row.started_at?.slice?.(0, 19) || "—"}</td><td>{row.models_promoted}</td><td className="text-[#f85149]">{row.error_message || "—"}</td></tr>
          ))}</tbody>
        </table>
      )}

      {tab === "backtests" && (
        <div className="space-y-3">{data.backtests.map((row) => (
          <article key={row.id} className="rounded border border-[#30363d] bg-[#161b22] p-4 text-sm">
            <div className="flex justify-between"><strong>{row.symbol} · {row.interval}</strong><span>{row.passed_promotion_gate ? "PASS" : "NOT PROMOTED"}</span></div>
            <div className="mt-2 grid gap-2 md:grid-cols-4">
              {[
                ["Precision", metric(row.precision)], ["Recall", metric(row.recall)], ["F1", metric(row.f1)],
                ["Profit factor", metric(row.profit_factor, 2)], ["Expectancy", metric(row.expectancy)],
                ["Sharpe", metric(row.sharpe_ratio, 2)], ["Maximum drawdown", metric(row.max_drawdown, 2)],
              ].map(([label, value]) => <div key={label}><span className="text-[#8b949e]">{label}: </span>{value}</div>)}
            </div>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <pre className="rounded bg-[#0d1117] p-2 text-xs">Confusion matrix{"\n"}{JSON.stringify(row.confusion_matrix || "—", null, 2)}</pre>
              <div>{(row.feature_importance || []).slice(0, 10).map((item) => (
                <div key={item.feature} className="mb-1 flex justify-between text-xs"><span>{item.feature}</span><span>{metric(item.importance, 4)}</span></div>
              ))}</div>
            </div>
          </article>
        ))}</div>
      )}

      {tab === "datasets" && (
        <table className="w-full text-left text-sm">
          <thead className="text-[#8b949e]"><tr><th className="pb-2">Version</th><th>Tier</th><th>Records</th><th>Status</th><th>Hash</th><th>Created</th></tr></thead>
          <tbody>{(monitoring.datasets || []).map((row) => (
            <tr key={row.id} className="border-t border-[#30363d]"><td className="py-2">{row.version_tag}</td><td>{row.tier}</td><td>{row.record_count}</td><td>{row.status}</td><td className="font-mono text-xs">{row.content_hash?.slice(0, 12)}</td><td>{row.created_at?.slice?.(0, 19)}</td></tr>
          ))}</tbody>
        </table>
      )}

      {tab === "promotions" && (
        <div className="space-y-3">{(monitoring.promotion_history || []).map((row) => (
          <article key={row.id} className="rounded border border-[#30363d] bg-[#161b22] p-4 text-sm">
            <div className="flex justify-between"><strong>Candidate #{row.candidate_model_version_id}</strong><span className={row.statistically_better ? "text-[#3fb950]" : "text-[#f85149]"}>{row.statistically_better ? "IMPROVED" : "REJECTED"}</span></div>
            <p className="mt-1 text-xs text-[#8b949e]">{(row.reasons || []).join("; ") || "All promotion gates passed"}</p>
          </article>
        ))}</div>
      )}
    </div>
  );
}
