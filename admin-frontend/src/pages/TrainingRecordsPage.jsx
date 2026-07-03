import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import {
  formatFeedbackLabel,
  formatMarketDirection,
  formatTimestamp,
} from "../utils/formatters.js";

const STATUSES = ["", "PENDING_REVIEW", "APPROVED", "REJECTED", "NEEDS_MORE_DATA"];

export default function TrainingRecordsPage() {
  const [records, setRecords] = useState([]);
  const [filter, setFilter] = useState("PENDING_REVIEW");
  const [expanded, setExpanded] = useState(null);
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadRecords = useCallback(async (status = filter) => {
    setLoading(true);
    setError("");
    try {
      const q = status ? `?status=${status}` : "";
      const data = await api(`/training-records${q}`);
      setRecords(data.records || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadRecords(filter);
  }, [filter, loadRecords]);

  async function review(id, admin_status) {
    setError("");
    try {
      await api(`/training-records/${id}/review`, {
        method: "PATCH",
        body: JSON.stringify({
          admin_status,
          admin_notes: notes[id] || undefined,
          label_quality_score: admin_status === "APPROVED" ? 0.8 : 0.3,
        }),
      });
      setNotice(`Record ${id} → ${admin_status}`);
      await loadRecords(filter);
    } catch (e) {
      setError(e.message);
    }
  }

  async function exportApproved() {
    setError("");
    try {
      const data = await api("/training-records/export");
      const blob = new Blob([JSON.stringify(data.records, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `training-records-approved-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice(`Exported ${data.count ?? data.records?.length ?? 0} approved records`);
    } catch (e) {
      setError(e.message);
    }
  }

  if (loading && !records.length) return <p className="text-[#8b949e]">Loading…</p>;

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Training records</h1>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="mb-4 flex flex-wrap gap-2">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s || "all"} value={s}>{s || "All statuses"}</option>
          ))}
        </select>
        <button type="button" onClick={exportApproved} className="rounded border border-[#30363d] px-3 py-2 text-sm hover:bg-[#21262d]">
          Export approved
        </button>
      </div>
      <div className="space-y-3">
        {records.map((r) => (
          <div key={r.id} className="rounded-lg border border-[#30363d] bg-[#161b22] p-4 text-sm">
            <button
              type="button"
              onClick={() => setExpanded(expanded === r.id ? null : r.id)}
              className="mb-2 flex w-full flex-wrap items-center justify-between gap-2 text-left"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">#{r.id}</span>
                <span className="text-[#8b949e]">prediction {r.prediction_id}</span>
                {r.conflict && (
                  <span className="rounded bg-[#3d1d20] px-2 py-0.5 text-xs text-[#f85149]">conflict</span>
                )}
                <span className="rounded bg-[#21262d] px-2 py-0.5 text-xs">{r.admin_status}</span>
              </div>
              <span className="text-xs text-[#8b949e]">{expanded === r.id ? "▲" : "▼"}</span>
            </button>
            <p className="text-[#8b949e]">
              User: <strong className="text-white">{r.username || "—"}</strong>
              {" · "}{r.symbol} · {r.predicted_action}
            </p>
            <p className="text-[#8b949e]">
              You: {formatFeedbackLabel(r.user_feedback)} · Market: {formatMarketDirection(r.market_direction)} ({r.market_outcome || "—"})
            </p>
            {expanded === r.id && (
              <div className="mt-3 border-t border-[#30363d] pt-3 text-xs text-[#8b949e]">
                <div className="mb-2 grid gap-1 sm:grid-cols-2">
                  <span>Market label: {r.label_from_market ?? "—"}</span>
                  <span>User label: {r.label_from_user ?? "—"}</span>
                  <span>Final label: {r.final_label ?? "—"}</span>
                  <span>Quality score: {r.label_quality_score ?? "—"}</span>
                  <span>Reviewed: {formatTimestamp(r.reviewed_at)}</span>
                  <span>Created: {formatTimestamp(r.created_at)}</span>
                </div>
                {r.admin_notes && <p className="mb-2">Notes: {r.admin_notes}</p>}
              </div>
            )}
            {r.admin_status === "PENDING_REVIEW" && (
              <>
                <textarea
                  value={notes[r.id] ?? ""}
                  onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                  placeholder="Admin notes (optional)"
                  className="mt-2 w-full rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-xs"
                  rows={2}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" onClick={() => review(r.id, "APPROVED")} className="rounded bg-[#238636] px-3 py-1 text-xs text-white">
                    Approve
                  </button>
                  <button type="button" onClick={() => review(r.id, "REJECTED")} className="rounded bg-[#da3633] px-3 py-1 text-xs text-white">
                    Reject
                  </button>
                  <button type="button" onClick={() => review(r.id, "NEEDS_MORE_DATA")} className="rounded border border-[#30363d] px-3 py-1 text-xs">
                    Needs data
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {!records.length && <p className="text-[#8b949e]">No records in this queue.</p>}
      </div>
    </div>
  );
}
