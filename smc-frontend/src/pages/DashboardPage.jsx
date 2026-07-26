import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../context/auth.js";

export default function DashboardPage() {
  const { setProfile } = useAuth();
  const [me, setMe] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/me"), api("/my/reviews?limit=20")])
      .then(([profile, rev]) => {
        setMe(profile);
        setProfile(profile);
        setReviews(rev.reviews || []);
      })
      .catch((err) => setError(err.message));
  }, [setProfile]);

  if (error) return <p className="text-red-400">{error}</p>;
  if (!me) return <p className="text-slate-400">Loading…</p>;

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Dashboard</h1>
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Username</p>
          <p className="font-medium">{me.username}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Status</p>
          <p className="font-medium capitalize">{me.status}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-xs text-slate-400">Signals remaining</p>
          <p className="font-medium">{me.signals_remaining}</p>
        </div>
      </div>

      <h2 className="mb-2 font-medium">Recent prediction reviews</h2>
      {reviews.length === 0 ? (
        <p className="text-sm text-slate-400">No predictions yet — run one from the Predict tab.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Correct?</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((r) => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="px-3 py-2">{r.symbol}</td>
                  <td className="px-3 py-2">{r.predicted_action}</td>
                  <td className="px-3 py-2">{r.status}</td>
                  <td className="px-3 py-2">{r.was_correct == null ? "—" : r.was_correct ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
