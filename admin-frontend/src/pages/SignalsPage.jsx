import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { withNotice } from "../hooks/usePageLoad.js";

export default function SignalsPage() {
  const [filter, setFilter] = useState("");
  const [signals, setSignals] = useState([]);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ symbol: "EURUSD", side: "BUY", entry_price: "1.085", confidence: "0.9" });

  async function loadSignals() {
    setLoading(true);
    setActionError("");
    try {
      const d = await api(`/signals${filter ? `?symbol=${encodeURIComponent(filter)}` : ""}`);
      setSignals(d.signals || []);
    } catch (e) {
      setActionError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSignals();
  }, []);

  async function create() {
    try {
      await withNotice(
        setNotice,
        setActionError,
        () =>
          api("/signals", {
            method: "POST",
            body: JSON.stringify({
              symbol: form.symbol,
              side: form.side,
              entry_price: parseFloat(form.entry_price),
              confidence: parseFloat(form.confidence),
            }),
          }),
        "Signal created"
      );
      await loadSignals();
    } catch {
      /* shown in banner */
    }
  }

  async function removeSignal(id) {
    if (!confirm(`Remove signal #${id}?`)) return;
    try {
      await withNotice(setNotice, setActionError, () => api(`/signals/${id}`, { method: "DELETE" }), "Signal removed");
      await loadSignals();
    } catch {
      /* banner */
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Signals</h1>
      <div className="mb-4 flex gap-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter symbol" className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-1.5 text-sm" />
        <button onClick={loadSignals} disabled={loading} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white disabled:opacity-50">{loading ? "Loading…" : "Refresh"}</button>
      </div>
      <PageAlerts error={actionError} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="mb-6 flex flex-wrap gap-2 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" placeholder="Symbol" />
        <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          <option>BUY</option><option>SELL</option>
        </select>
        <input value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" placeholder="Entry" />
        <input value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" placeholder="Confidence" />
        <button type="button" onClick={create} className="rounded bg-[#2f81f7] px-3 py-1 text-sm text-white">Create manual signal</button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="text-left text-[#8b949e]"><tr><th className="p-2">ID</th><th>User</th><th>Symbol</th><th>Side</th><th>Conf</th><th>Entry</th><th>Timeframe</th><th>Status</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.id} className="border-t border-[#30363d]">
                <td className="p-2">{s.id}</td><td>{s.user_id ?? "-"}</td><td>{s.symbol}</td><td>{s.side}</td>
                <td>{s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : "-"}</td>
                <td>{s.entry_price}</td><td>{s.timeframe ?? "-"}</td><td>{s.status ?? "-"}</td>
                <td className="text-xs text-[#8b949e]">{s.created_at ? String(s.created_at).slice(0, 19) : "-"}</td>
                <td>
                  <button type="button" onClick={() => removeSignal(s.id)} className="text-xs text-[#f85149] hover:underline">Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
