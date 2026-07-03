import { Fragment, useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { usePageLoad, withNotice } from "../hooks/usePageLoad.js";
import {
  formatFeedbackLabel,
  formatMarketDirection,
  formatReviewStatus,
  formatTimestamp,
} from "../utils/formatters.js";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState([]);
  const [status, setStatus] = useState("evaluated");
  const [expanded, setExpanded] = useState(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");

  const loadReviews = useCallback(async () => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    const d = await api(`/reviews${q}`);
    setReviews(d.reviews || []);
  }, [status]);

  const { loading, error, reload } = usePageLoad(loadReviews, [status]);

  async function retrain(id, promote = true) {
    if (!confirm(promote ? "Retrain and promote model from this review?" : "Retrain without promoting?")) return;
    try {
      await withNotice(
        setNotice,
        setActionError,
        () => api(`/reviews/${id}/retrain`, { method: "POST", body: JSON.stringify({ promote }) }),
        promote ? "Retrained and promoted" : "Retrained (not promoted)"
      );
      await reload();
    } catch {
      /* banner */
    }
  }

  async function dismiss(id) {
    if (!confirm("Dismiss this review (skip retrain)?")) return;
    try {
      await withNotice(setNotice, setActionError, () => api(`/reviews/${id}/dismiss`, { method: "POST" }), "Review dismissed");
      await reload();
    } catch {
      /* banner */
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Prediction Reviews (2h)</h1>
      <p className="mb-4 text-sm text-[#8b949e]">
        User feedback is due 2 hours after each prediction. Market verification runs after the window. Retrain from evaluated outcomes or dismiss reviews you do not want in training.
      </p>
      <div className="mb-4 flex gap-2">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          <option value="evaluated">Evaluated (needs action)</option>
          <option value="pending">Pending evaluation</option>
          <option value="retrain_done">Retrain done</option>
          <option value="dismissed">Dismissed</option>
          <option value="">All</option>
        </select>
        <button type="button" onClick={reload} disabled={loading} className="rounded bg-[#2f81f7] px-3 py-1 text-sm text-white disabled:opacity-50">{loading ? "Loading…" : "Refresh"}</button>
      </div>
      <PageAlerts error={error || actionError} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="bg-[#161b22] text-left text-[#8b949e]">
            <tr>
              <th className="p-2">ID</th><th>Symbol</th><th>Predicted</th><th>Actual</th><th>Correct</th><th>Status</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {reviews.length === 0 && !loading && (
              <tr><td colSpan={7} className="p-4 text-center text-[#8b949e]">No reviews in this filter</td></tr>
            )}
            {reviews.map((r) => (
              <Fragment key={r.id}>
                <tr
                  className="cursor-pointer border-t border-[#30363d] hover:bg-[#161b22]/80"
                  onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                >
                  <td className="p-2">{r.id}</td>
                  <td>{r.symbol}</td>
                  <td>{r.predicted_action} ({((r.predicted_confidence || 0) * 100).toFixed(0)}%)</td>
                  <td>{formatMarketDirection(r.actual_direction)}</td>
                  <td>{r.was_correct == null ? "-" : r.was_correct ? "yes" : "no"}</td>
                  <td>
                    {formatReviewStatus(r.status)}
                    {r.conflict && <span className="ml-1 text-[#f85149]">· conflict</span>}
                  </td>
                  <td className="space-x-1 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    {r.status === "evaluated" && (
                      <>
                        <button type="button" onClick={() => retrain(r.id, true)} className="rounded bg-[#238636] px-2 py-0.5 text-xs text-white">Retrain + promote</button>
                        <button type="button" onClick={() => retrain(r.id, false)} className="rounded border border-[#30363d] px-2 py-0.5 text-xs">Retrain only</button>
                        <button type="button" onClick={() => dismiss(r.id)} className="rounded border border-[#f85149] px-2 py-0.5 text-xs text-[#f85149]">Skip</button>
                      </>
                    )}
                  </td>
                </tr>
                {expanded === r.id && (
                  <tr className="border-t border-[#30363d] bg-[#0d1117]">
                    <td colSpan={7} className="p-4 text-sm text-[#8b949e]">
                      <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        <span>Entry: {r.entry_price?.toFixed?.(5) ?? r.entry_price ?? "—"}</span>
                        <span>Actual price: {r.actual_price?.toFixed?.(5) ?? "—"}</span>
                        <span>Feedback due: {formatTimestamp(r.feedback_due_at)}</span>
                        <span>Evaluated: {formatTimestamp(r.evaluated_at)}</span>
                        <span>User feedback: {formatFeedbackLabel(r.user_feedback)}</span>
                        <span>Market outcome: {r.market_outcome ?? "—"}</span>
                      </div>
                      {r.user_comment && <p className="mb-2">Comment: {r.user_comment}</p>}
                      {r.conflict && (
                        <p className="mb-2 text-[#f85149]">
                          User feedback conflicts with market direction.{" "}
                          <Link to="/training-records" className="text-[#2f81f7] hover:underline">View training records</Link>
                        </p>
                      )}
                      {r.component_scores && Object.keys(r.component_scores).length > 0 && (
                        <div className="mb-2">
                          <p className="mb-1 font-medium text-[#e6edf3]">Component scores</p>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(r.component_scores).map(([k, v]) => (
                              <span key={k} className="rounded bg-[#21262d] px-2 py-0.5 text-xs">{k}: {typeof v === "number" ? v.toFixed(2) : v}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {r.market_verification && (
                        <div>
                          <p className="mb-1 font-medium text-[#e6edf3]">Market verification</p>
                          <span className="mr-3">MFE: {r.market_verification.mfe ?? "—"}</span>
                          <span className="mr-3">MAE: {r.market_verification.mae ?? "—"}</span>
                          <span>Invalidation hit: {r.market_verification.invalidation_hit ? "yes" : "no"}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
