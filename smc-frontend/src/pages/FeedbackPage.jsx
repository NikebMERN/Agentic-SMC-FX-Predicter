import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import OutcomeFeedback, { outcomeLabel } from "../components/OutcomeFeedback.jsx";
import { tradeEntryLabel } from "../components/TradeEntryFeedback.jsx";

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

  async function submitOutcome(reviewId, feedback) {
    setBusyId(reviewId);
    setError("");
    try {
      const res = await api(`/my/reviews/${reviewId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback, kind: "outcome" }),
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

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold">My account & prediction outcomes</h1>
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

      <p className="mb-4 text-sm text-slate-400">
        Rate how your trades went — successful, failed, or didn&apos;t take. Mark whether you entered a signal on the{" "}
        <Link to="/predict" className="text-sky-400 hover:underline">Predict</Link> page after each analysis.
        {" "}
        <Link to="/history" className="text-sky-400 hover:underline">View history & charts</Link>
      </p>

      <h2 className="mb-2 font-medium">Recent predictions</h2>
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
                {r.user_trade_entry && ` · Entry: ${tradeEntryLabel(r.user_trade_entry)}`}
                {r.user_feedback && ` · Outcome: ${outcomeLabel(r.user_feedback)}`}
                {r.conflict && " · ⚠ Conflict — flagged for admin"}
              </p>
              <OutcomeFeedback
                review={r}
                busy={busyId === r.id}
                onSubmit={submitOutcome}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
