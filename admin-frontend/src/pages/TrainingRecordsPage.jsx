import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import {
  formatFeedbackLabel,
  formatMarketDirection,
  formatTimestamp,
} from "../utils/formatters.js";

const STATUSES = [
  ["CONFLICTS", "Needs your review (conflicts)"],
  ["APPROVED", "In training ground (auto-approved)"],
  ["", "All statuses"],
  ["NEEDS_MORE_DATA", "Needs more data"],
  ["REJECTED", "Rejected"],
  ["READY", "Training-ready only"],
];

function formatQuality(score) {
  if (score == null || score === "") return "—";
  const n = Number(score);
  return Number.isFinite(n) ? n.toFixed(2) : String(score);
}

export default function TrainingRecordsPage() {
  const [records, setRecords] = useState([]);
  const [filter, setFilter] = useState("CONFLICTS");
  const [expanded, setExpanded] = useState(null);
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadRecords = useCallback(async (status = filter, refresh = false) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (status === "READY") {
        params.set("ready", "1");
      } else if (status === "CONFLICTS") {
        params.set("conflicts", "1");
      } else if (status) {
        params.set("status", status);
      }
      if (refresh) params.set("refresh", "1");
      const q = params.toString() ? `?${params}` : "";
      const data = await api(`/training-records${q}`);
      setRecords(data.records || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadRecords(filter, true);
  }, [filter, loadRecords]);

  const stats = useMemo(() => {
    const ready = records.filter((r) => r.training_ready).length;
    const conflicts = records.filter((r) => r.needs_manual_review).length;
    const approved = records.filter((r) => r.admin_status === "APPROVED").length;
    return { ready, conflicts, approved };
  }, [records]);

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

  async function govern(id, changes) {
    setError("");
    try {
      await api(`/training-records/${id}/governance`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setNotice(`Record ${id} governance updated`);
      await loadRecords(filter);
    } catch (e) {
      setError(e.message);
    }
  }

  async function exportDataset() {
    setError("");
    try {
      const data = await api("/training-records/dataset");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `training-dataset-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice(`Exported ${data.count ?? 0} cross-checked training samples`);
    } catch (e) {
      setError(e.message);
    }
  }

  if (loading && !records.length) return <p className="text-[#8b949e]">Loading…</p>;

  return (
    <div>
      <h1 className="mb-2 text-lg font-semibold">Training records</h1>
      <p className="mb-4 max-w-3xl text-sm text-[#8b949e]">
        Matching user feedback and market data is automatic. Clean records go straight to the training ground —
        you only need to approve or reject when there is a <strong className="text-[#e6edf3]">conflict</strong>.
      </p>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-3">
          <div className="text-xl font-bold text-[#3fb950]">{stats.ready}</div>
          <div className="text-xs text-[#8b949e]">Training-ready in view</div>
        </div>
        <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-3">
          <div className="text-xl font-bold text-[#f85149]">{stats.conflicts}</div>
          <div className="text-xs text-[#8b949e]">Awaiting your decision</div>
        </div>
        <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-3">
          <div className="text-xl font-bold">{stats.approved}</div>
          <div className="text-xs text-[#8b949e]">Auto-approved for training</div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm"
        >
          {STATUSES.map(([value, label]) => (
            <option key={value || "all"} value={value}>{label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => loadRecords(filter, true)}
          disabled={loading}
          className="rounded border border-[#30363d] px-3 py-2 text-sm hover:bg-[#21262d] disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh cross-check"}
        </button>
        <button
          type="button"
          onClick={exportDataset}
          className="rounded bg-[#238636] px-3 py-2 text-sm text-white hover:bg-[#2ea043]"
        >
          Export training dataset
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
                <span className="text-[#8b949e]">{r.symbol} · {r.interval} · prediction {r.prediction_id}</span>
                {r.training_ready && (
                  <span className="rounded bg-[#1a3d2a] px-2 py-0.5 text-xs text-[#3fb950]">training ready</span>
                )}
                {r.auto_approved && (
                  <span className="rounded bg-[#1a3d2a] px-2 py-0.5 text-xs text-[#3fb950]">auto-approved</span>
                )}
                {r.needs_manual_review && (
                  <span className="rounded bg-[#3d1d20] px-2 py-0.5 text-xs text-[#f85149]">needs review</span>
                )}
                <span className="rounded bg-[#21262d] px-2 py-0.5 text-xs">{r.admin_status}</span>
              </div>
              <span className="text-xs text-[#8b949e]">{expanded === r.id ? "▲" : "▼"}</span>
            </button>

            <p className="text-[#8b949e]">
              User: <strong className="text-white">{r.username || "—"}</strong>
              {" · "}{r.predicted_action}
              {" · "}Final label: <strong className="text-white">{r.final_label ?? "—"}</strong>
              {" · "}Quality: <strong className="text-white">{formatQuality(r.label_quality_score)}</strong>
            </p>
            <p className="text-[#8b949e]">
              You: {formatFeedbackLabel(r.user_feedback)} · Market: {formatMarketDirection(r.market_direction)} ({r.market_outcome || "—"})
            </p>
            {r.cross_check?.summary && (
              <p className="mt-1 text-xs text-[#6e7681]">Cross-check: {r.cross_check.summary}</p>
            )}

            {expanded === r.id && (
              <div className="mt-3 border-t border-[#30363d] pt-3 text-xs text-[#8b949e]">
                <div className="mb-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
                  <span>Market label: {r.label_from_market ?? "—"}</span>
                  <span>User label: {r.label_from_user ?? "—"}</span>
                  <span>Final label: {r.final_label ?? "—"}</span>
                  <span>Quality score: {formatQuality(r.label_quality_score)}</span>
                  <span>Interval: {r.interval ?? "—"}</span>
                  <span>Reviewed: {formatTimestamp(r.reviewed_at)}</span>
                  <span>Dataset: {r.dataset_tier ?? "PENDING_REVIEW"}</span>
                  <span>Validation: {formatQuality(r.validation_score)}</span>
                  <span>Suspicious: {r.suspicious ? "yes" : "no"}</span>
                </div>
                {r.validation_reasons?.length > 0 && (
                  <p className="mb-2 text-[#f0883e]">Validation: {r.validation_reasons.join("; ")}</p>
                )}
                <div className="mb-3 flex flex-wrap gap-2">
                  <select
                    value={r.dataset_tier || "PENDING_REVIEW"}
                    onChange={(e) => govern(r.id, { dataset_tier: e.target.value })}
                    className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1"
                  >
                    {["PENDING_REVIEW", "APPROVED", "REJECTED", "GOLD"].map((tier) => (
                      <option key={tier} value={tier}>{tier}</option>
                    ))}
                  </select>
                  <button type="button" onClick={() => govern(r.id, { suspicious: !r.suspicious })} className="rounded border border-[#30363d] px-2 py-1">
                    {r.suspicious ? "Clear suspicious" : "Flag suspicious"}
                  </button>
                  <button type="button" onClick={() => govern(r.id, { institutional_example: !r.institutional_example })} className="rounded border border-[#30363d] px-2 py-1">
                    {r.institutional_example ? "Remove institutional mark" : "Mark institutional"}
                  </button>
                </div>
                {r.admin_notes && <p className="mb-2">Notes: {r.admin_notes}</p>}
                {r.training_sample ? (
                  <div>
                    <p className="mb-1 font-medium text-[#e6edf3]">Raw training sample</p>
                    <pre className="max-h-64 overflow-auto rounded border border-[#30363d] bg-[#0d1117] p-2 text-[11px] leading-relaxed text-[#c9d1d9]">
                      {JSON.stringify(r.training_sample, null, 2)}
                    </pre>
                  </div>
                ) : (
                  <p className="text-[#f0883e]">Not enough cross-checked data to build a training row yet.</p>
                )}
              </div>
            )}

            {r.needs_manual_review && (
              <>
                <p className="mt-2 text-xs text-[#f85149]">
                  User feedback disagrees with market — choose whether to trust the user or the market label.
                </p>
                <textarea
                  value={notes[r.id] ?? ""}
                  onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                  placeholder="Admin notes (optional)"
                  className="mt-2 w-full rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-xs"
                  rows={2}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" onClick={() => review(r.id, "APPROVED")} className="rounded bg-[#238636] px-3 py-1 text-xs text-white">
                    Approve (use market label)
                  </button>
                  <button type="button" onClick={() => review(r.id, "REJECTED")} className="rounded bg-[#da3633] px-3 py-1 text-xs text-white">
                    Reject
                  </button>
                </div>
              </>
            )}

            {r.admin_status === "APPROVED" && !r.needs_manual_review && (
              <p className="mt-2 text-xs text-[#3fb950]">
                Sent to training ground automatically — no action needed.
              </p>
            )}
          </div>
        ))}
        {!records.length && (
          <p className="text-[#8b949e]">
            {filter === "CONFLICTS"
              ? "No conflicts waiting — clean records are auto-approved."
              : "No records in this filter."}
          </p>
        )}
      </div>
    </div>
  );
}
