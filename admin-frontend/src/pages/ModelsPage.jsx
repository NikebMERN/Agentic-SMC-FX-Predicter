import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { usePageLoad, withNotice } from "../hooks/usePageLoad.js";

export default function ModelsPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [models, setModels] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [backtest, setBacktest] = useState(null);
  const [refreshRunning, setRefreshRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");

  const loadAll = useCallback(async () => {
    const d = await api("/models");
    setModels(d.models || []);
    const c = await api("/models/candidates");
    setCandidates(c.candidates || []);
    try {
      const st = await api("/data/refresh/status");
      setRefreshRunning(Boolean(st.running));
    } catch {
      /* ignore */
    }
  }, []);

  const { loading, error, reload } = usePageLoad(loadAll, []);

  useEffect(() => {
    if (!refreshRunning) return;
    const id = window.setInterval(async () => {
      try {
        const st = await api("/data/refresh/status");
        setRefreshRunning(Boolean(st.running));
        if (!st.running) {
          setNotice("Refresh-all completed");
          await reload();
        }
      } catch {
        /* ignore */
      }
    }, 3000);
    return () => window.clearInterval(id);
  }, [refreshRunning, reload]);

  async function runAction(fn, msg) {
    try {
      await withNotice(setNotice, setActionError, fn, msg);
      await reload();
    } catch {
      /* banner */
    }
  }

  async function retrain() {
    await runAction(() => api("/models/retrain", { method: "POST", body: JSON.stringify({ symbol }) }), `${symbol} retrained`);
  }

  async function promote(versionId) {
    if (!confirm(`Promote model version ${versionId}?`)) return;
    await runAction(() => api(`/models/versions/${versionId}/promote`, { method: "POST" }), "Model promoted");
  }

  async function refreshPair() {
    try {
      const r = await withNotice(
        setNotice,
        setActionError,
        () => api("/data/refresh", { method: "POST", body: JSON.stringify({ symbol }) }),
        `${symbol} refreshed`
      );
      setNotice(r.message || `${symbol} refreshed`);
    } catch {
      /* banner */
    }
  }

  async function refreshAll() {
    if (!confirm("Refresh ALL pairs in background?")) return;
    try {
      await withNotice(
        setNotice,
        setActionError,
        () => api("/data/refresh", { method: "POST", body: JSON.stringify({ all: true }) }),
        "Refresh started"
      );
      setRefreshRunning(true);
    } catch {
      /* banner */
    }
  }

  async function delModel(name) {
    if (!confirm(`Delete ${name}?`)) return;
    await runAction(() => api(`/models/${encodeURIComponent(name)}`, { method: "DELETE" }), `${name} deleted`);
  }

  async function runBacktest() {
    setActionError("");
    try {
      const r = await api("/backtest", { method: "POST", body: JSON.stringify({ symbol, fetch: false }) });
      setBacktest(r);
      setNotice(r.saved_to_report ? `Backtest saved — see Dashboard` : `Backtest complete for ${symbol}`);
    } catch (e) {
      setActionError(e.message);
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Models &amp; Data</h1>
      <p className="mb-4 text-sm text-[#8b949e]">
        New models are saved as <strong>candidates</strong> until you promote them. Use AI Reviews to retrain from real outcomes.
      </p>
      <PageAlerts error={error || actionError} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} className="w-28 rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
        <button type="button" onClick={retrain} className="rounded bg-[#2f81f7] px-3 py-1 text-sm text-white">Fetch + retrain</button>
        <button type="button" onClick={refreshPair} className="rounded border border-[#30363d] px-3 py-1 text-sm">Refresh CSV</button>
        <button type="button" onClick={refreshAll} disabled={refreshRunning} className="rounded border border-[#30363d] px-3 py-1 text-sm disabled:opacity-50">
          {refreshRunning ? "Refreshing all…" : "Refresh ALL"}
        </button>
        <button type="button" onClick={reload} disabled={loading} className="rounded border border-[#30363d] px-3 py-1 text-sm disabled:opacity-50">{loading ? "Loading…" : "Reload list"}</button>
        <button type="button" onClick={runBacktest} className="rounded border border-[#30363d] px-3 py-1 text-sm">Backtest</button>
      </div>
      {backtest && !backtest.error && (
        <div className="mb-4 rounded-lg border border-[#30363d] bg-[#161b22] p-4 text-sm">
          <h2 className="mb-2 font-medium">Backtest — {backtest.symbol}</h2>
          <div className="grid gap-1 text-[#8b949e] sm:grid-cols-2 lg:grid-cols-4">
            <span>Win rate: {((backtest.win_rate ?? 0) * 100).toFixed(1)}%</span>
            <span>Trades: {backtest.trades ?? 0}</span>
            <span>Avg RR: {backtest.avg_rr ?? "—"}</span>
            <span>Max drawdown: {backtest.max_drawdown_pct ?? "—"}%</span>
          </div>
        </div>
      )}
      {backtest?.error && <p className="mb-4 text-sm text-[#f85149]">{backtest.error}</p>}
      {candidates.length > 0 && (
        <>
          <h2 className="mb-2 text-sm font-semibold text-[#8b949e]">Candidates (promote to production)</h2>
          <div className="mb-4 overflow-x-auto rounded-lg border border-[#30363d]">
            <table className="w-full text-sm">
              <thead className="text-left text-[#8b949e]">
                <tr><th className="p-2">ID</th><th>Symbol</th><th>Val acc</th><th>Samples</th><th></th></tr>
              </thead>
              <tbody>
                {candidates.map((m) => (
                  <tr key={m.id} className="border-t border-[#30363d]">
                    <td className="p-2">{m.id}</td>
                    <td>{m.symbol}</td>
                    <td>{m.val_accuracy != null ? `${(m.val_accuracy * 100).toFixed(1)}%` : "-"}</td>
                    <td>{m.samples ?? "-"}</td>
                    <td>
                      <button type="button" onClick={() => promote(m.id)} className="rounded bg-[#238636] px-2 py-0.5 text-xs text-white">Promote</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="text-left text-[#8b949e]">
            <tr><th className="p-2">File</th><th>Symbol</th><th>Source</th><th>Active</th><th>Samples</th><th>Val acc</th><th></th></tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={`${m.file}-${m.id || "disk"}`} className="border-t border-[#30363d]">
                <td className="p-2">{m.file}</td>
                <td>{m.symbol ?? "-"}</td>
                <td>{m.source ?? "disk"}</td>
                <td>{m.active ? "yes" : "-"}</td>
                <td>{m.metrics?.samples ?? "-"}</td>
                <td>{m.metrics?.val_accuracy != null ? `${(m.metrics.val_accuracy * 100).toFixed(1)}%` : "-"}</td>
                <td>{m.file?.endsWith(".joblib") && <button type="button" onClick={() => delModel(m.file)} className="text-xs text-[#f85149]">Delete</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
