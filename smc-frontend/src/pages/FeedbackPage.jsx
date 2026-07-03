import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";

const FEEDBACK_OPTIONS = [
  { value: "SUCCESSFUL", label: "Successful" },
  { value: "FAILED", label: "Failed" },
  { value: "DID_NOT_TAKE", label: "Didn't take" },
];

export default function FeedbackPage() {
  const { setProfile } = useAuth();
  const [me, setMe] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  async function load() {
    const [user, rev] = await Promise.all([api("/me"), api("/my/reviews?limit=50")]);
    setMe(user);
    setProfile(user);
    setReviews(rev.reviews || []);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [setProfile]);

  async function submitFeedback(reviewId, feedback) {
    setBusyId(reviewId);
    setError("");
    try {
      const res = await api(`/my/reviews/${reviewId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback }),
      });
      if (res.message?.includes("differs from market")) {
        setError(res.message);
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error && !me) return <p className="mx-auto max-w-4xl px-4 py-6 text-red-400">{error}</p>;
  if (!me) return <p className="mx-auto max-w-4xl px-4 py-6 text-slate-400">Loading…</p>;

  const pendingFeedback = reviews.filter((r) => r.feedback_required);

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold">My account & feedback</h1>
      {error && <p className="mb-3 text-sm text-red-400">{error}</p>}

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Username</p>
          <p className="font-medium">{me.username}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Free trial quota</p>
          <p className="font-medium">{me.signals_remaining} remaining (web + Telegram)</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Status</p>
          <p className="font-medium capitalize">{me.status}</p>
        </div>
      </div>

      {pendingFeedback.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-700/50 bg-amber-950/30 p-4 text-sm text-amber-100">
          <strong>{pendingFeedback.length}</strong> prediction(s) need your feedback (due 2 hours after each run).
        </div>
      )}

      <p className="mb-4 text-sm text-slate-400">
        After 2 hours, rate each prediction. We cross-check your answer with market data and flag mismatches for admin review.{" "}
        <Link to="/history" className="text-sky-400 hover:underline">View history & charts</Link>
        {" · "}
        <Link to="/predict" className="text-sky-400 hover:underline">Run a new analysis</Link>
      </p>

      <h2 className="mb-2 font-medium">Prediction feedback history</h2>
      {reviews.length === 0 ? (
        <p className="text-sm text-slate-400">No prediction reviews yet.</p>
      ) : (
        <div className="space-y-3">
          {reviews.map((r) => (
            <div key={r.id} className="rounded-lg border border-slate-700 bg-slate-900 p-4 text-sm">
              <div className="mb-2 flex flex-wrap justify-between gap-2">
                <span>{r.symbol} · {r.predicted_action} · {(r.predicted_confidence * 100).toFixed(0)}%</span>
                <span className="text-slate-400">{r.predicted_at ? new Date(r.predicted_at).toLocaleString() : "—"}</span>
              </div>
              <p className="text-slate-400">
                Status: {r.status}
                {r.market_outcome && ` · Market: ${r.market_outcome} (${r.actual_direction || "?"})`}
                {r.user_feedback && ` · You: ${r.user_feedback}`}
                {r.conflict && " · ⚠ Conflict — flagged for admin"}
                {r.user_truthful === true && r.user_feedback && " · Matches market"}
                {r.user_truthful === false && " · Does not match market"}
              </p>
              {r.feedback_required && !r.user_feedback && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {FEEDBACK_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      disabled={busyId === r.id}
                      onClick={() => submitFeedback(r.id, opt.value)}
                      className="rounded border border-slate-600 px-2 py-1 text-xs hover:bg-slate-800 disabled:opacity-50"
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
