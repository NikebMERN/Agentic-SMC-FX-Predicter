import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import {
  formatFeedbackLabel,
  formatMarketDirection,
  formatReviewStatus,
  formatTimestamp,
  formatUserEmail,
  isTelegramEmail,
} from "../utils/formatters.js";

export default function UserDetailPage() {
  const { id } = useParams();
  const [detail, setDetail] = useState(null);
  const [history, setHistory] = useState(null);
  const [quota, setQuota] = useState("");
  const [tab, setTab] = useState("predictions");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [d, h] = await Promise.all([api(`/users/${id}`), api(`/users/${id}/history`)]);
      setDetail(d);
      setHistory(h);
      setQuota(String(d.user?.signals_remaining ?? 0));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveQuota() {
    setError("");
    try {
      const n = parseInt(quota, 10);
      if (Number.isNaN(n) || n < 0) return setError("Quota must be a non-negative number");
      await api(`/users/${id}/quota`, {
        method: "POST",
        body: JSON.stringify({ signals_remaining: n }),
      });
      setNotice("Quota updated");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (loading && !detail) return <p className="text-[#8b949e]">Loading…</p>;
  if (error && !detail) return <PageAlerts error={error} />;
  if (!detail) return null;

  const u = detail.user;
  const tabs = [
    ["predictions", "Predictions", history?.predictions?.length ?? 0],
    ["signals", "Signals", history?.signals?.length ?? 0],
    ["trades", "Trades", history?.trades?.length ?? 0],
    ["training", "Training", history?.training_records?.length ?? 0],
  ];

  return (
    <div>
      <Link to="/users" className="mb-4 inline-block text-sm text-[#2f81f7]">← Back to users</Link>
      <h1 className="mb-4 text-lg font-semibold">User #{u.id} — {u.username}</h1>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <InfoCard
          label="Email"
          value={formatUserEmail(u)}
          sub={isTelegramEmail(u) && u.email ? u.email : null}
          href={!isTelegramEmail(u) && u.email ? `mailto:${u.email}` : null}
        />
        <InfoCard label="Role" value={u.role} />
        <InfoCard label="Status" value={u.status || (u.is_active ? "active" : "pending")} />
        <InfoCard label="Telegram" value={detail.telegram?.linked ? `Linked (${detail.telegram.chat_id})` : "Not linked"} />
      </div>

      <div className="mb-6 flex flex-wrap items-end gap-2 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <div>
          <label className="mb-1 block text-xs text-[#8b949e]">Predictions quota</label>
          <input
            type="number"
            min="0"
            value={quota}
            onChange={(e) => setQuota(e.target.value)}
            className="w-28 rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm"
          />
        </div>
        <button type="button" onClick={saveQuota} className="rounded bg-[#2f81f7] px-3 py-1 text-sm text-white">
          Save quota
        </button>
        <span className="text-xs text-[#8b949e]">
          {detail.counts?.predictions ?? 0} predictions · {detail.counts?.trades ?? 0} trades · {detail.counts?.feedback ?? 0} feedback
        </span>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {tabs.map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded px-3 py-1 text-sm ${tab === key ? "bg-[#2f81f7] text-white" : "border border-[#30363d] text-[#8b949e]"}`}
          >
            {label} ({count})
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        {tab === "predictions" && (
          <table className="w-full text-sm">
            <thead className="text-left text-[#8b949e]">
              <tr><th className="p-2">ID</th><th>Symbol</th><th>Action</th><th>Correct</th><th>Status</th><th>When</th></tr>
            </thead>
            <tbody>
              {(history?.predictions || []).map((r) => (
                <tr key={r.id} className="border-t border-[#30363d]">
                  <td className="p-2">{r.id}</td>
                  <td>{r.symbol}</td>
                  <td>{r.predicted_action}</td>
                  <td>{r.was_correct == null ? "—" : r.was_correct ? "yes" : "no"}</td>
                  <td>{formatReviewStatus(r.status)}</td>
                  <td className="text-xs text-[#8b949e]">{formatTimestamp(r.predicted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "signals" && (
          <table className="w-full text-sm">
            <thead className="text-left text-[#8b949e]">
              <tr><th className="p-2">ID</th><th>Symbol</th><th>Side</th><th>Status</th><th>Created</th></tr>
            </thead>
            <tbody>
              {(history?.signals || []).map((s) => (
                <tr key={s.id} className="border-t border-[#30363d]">
                  <td className="p-2">{s.id}</td>
                  <td>{s.symbol}</td>
                  <td>{s.side}</td>
                  <td>{s.status}</td>
                  <td className="text-xs text-[#8b949e]">{formatTimestamp(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "trades" && (
          <table className="w-full text-sm">
            <thead className="text-left text-[#8b949e]">
              <tr><th className="p-2">ID</th><th>Symbol</th><th>Side</th><th>Status</th><th>PnL</th><th>Score</th></tr>
            </thead>
            <tbody>
              {(history?.trades || []).map((t) => (
                <tr key={t.id} className="border-t border-[#30363d]">
                  <td className="p-2">{t.id}</td>
                  <td>{t.symbol}</td>
                  <td>{t.side}</td>
                  <td>{t.status}</td>
                  <td>{t.pnl ?? "—"}</td>
                  <td>{t.outcome_score_label ?? t.outcome_score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "training" && (
          <table className="w-full text-sm">
            <thead className="text-left text-[#8b949e]">
              <tr><th className="p-2">ID</th><th>Prediction</th><th>Feedback</th><th>Market</th><th>Status</th><th>Conflict</th></tr>
            </thead>
            <tbody>
              {(history?.training_records || []).map((r) => (
                <tr key={r.id} className="border-t border-[#30363d]">
                  <td className="p-2">{r.id}</td>
                  <td>{r.prediction_id}</td>
                  <td>{formatFeedbackLabel(r.user_feedback)}</td>
                  <td>{formatMarketDirection(r.market_direction)}</td>
                  <td>{r.admin_status}</td>
                  <td>{r.conflict ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function InfoCard({ label, value, sub, href }) {
  return (
    <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
      <p className="text-xs text-[#8b949e]">{label}</p>
      {href ? (
        <a href={href} className="break-all font-medium text-[#2f81f7] hover:underline">
          {value ?? "—"}
        </a>
      ) : (
        <p className="break-all font-medium">{value ?? "—"}</p>
      )}
      {sub && <p className="mt-1 break-all text-[10px] text-[#6e7681]">{sub}</p>}
    </div>
  );
}
