import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client.js";
import PredictionHistoryChart from "../components/PredictionHistoryChart.jsx";

const OUTCOME_COLORS = {
  correct: "#22c55e",
  incorrect: "#ef4444",
  pending: "#64748b",
};

function outcomeLabel(review) {
  if (review.was_correct === true) return "Correct";
  if (review.was_correct === false) return "Incorrect";
  if (review.status === "pending" || review.status === "awaiting_feedback") return "Awaiting result";
  return "Pending";
}

function outcomeKey(review) {
  if (review.was_correct === true) return "correct";
  if (review.was_correct === false) return "incorrect";
  return "pending";
}

export default function HistoryPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [chartCache, setChartCache] = useState({});
  const [chartLoading, setChartLoading] = useState(null);

  useEffect(() => {
    api("/my/history?hours=24")
      .then(setData)
      .catch((err) => setError(err.message));
  }, []);

  const stats24 = data?.stats_24h;
  const reviews24 = data?.reviews_24h || [];

  const outcomeChart = useMemo(() => {
    if (!stats24) return [];
    return [
      { name: "Correct", value: stats24.correct, key: "correct" },
      { name: "Incorrect", value: stats24.incorrect, key: "incorrect" },
      { name: "Pending", value: stats24.pending, key: "pending" },
    ].filter((d) => d.value > 0);
  }, [stats24]);

  const actionChart = useMemo(() => {
    if (!stats24?.by_action) return [];
    return Object.entries(stats24.by_action).map(([name, value]) => ({ name, value }));
  }, [stats24]);

  async function toggleChart(reviewId) {
    if (expandedId === reviewId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(reviewId);
    if (chartCache[reviewId]) return;
    setChartLoading(reviewId);
    try {
      const chart = await api(`/my/reviews/${reviewId}/candles?bars=48`);
      setChartCache((prev) => ({ ...prev, [reviewId]: chart }));
    } catch (err) {
      setError(err.message);
    } finally {
      setChartLoading(null);
    }
  }

  if (error && !data) return <p className="mx-auto max-w-5xl px-4 py-6 text-red-400">{error}</p>;
  if (!data) return <p className="mx-auto max-w-5xl px-4 py-6 text-slate-400">Loading history…</p>;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Prediction history</h1>
          <p className="mt-1 text-sm text-slate-400">
            Last 24 hours · 60min timeframe · tap a row to see price chart with entry, target, and outcome.
          </p>
        </div>
        <Link to="/predict" className="rounded-md bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500">
          New prediction
        </Link>
      </div>

      {error && <p className="mb-3 text-sm text-red-400">{error}</p>}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Predictions (24h)" value={stats24?.total ?? 0} />
        <StatCard label="Correct" value={stats24?.correct ?? 0} accent="text-green-400" />
        <StatCard label="Incorrect" value={stats24?.incorrect ?? 0} accent="text-red-400" />
        <StatCard
          label="Accuracy (24h)"
          value={
            stats24?.accuracy != null ? `${(stats24.accuracy * 100).toFixed(0)}%` : "—"
          }
        />
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-300">Outcomes (24h)</h2>
          {outcomeChart.length === 0 ? (
            <p className="text-sm text-slate-500">No predictions in the last 24 hours.</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={outcomeChart} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
                  {outcomeChart.map((entry) => (
                    <Cell key={entry.key} fill={OUTCOME_COLORS[entry.key]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-300">By signal type (24h)</h2>
          {actionChart.length === 0 ? (
            <p className="text-sm text-slate-500">No data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={actionChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Bar dataKey="value" name="Count" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">Predictions in the last 24 hours</h2>
        <span className="text-xs text-slate-500">All-time total: {data.stats_all_time?.total ?? 0}</span>
      </div>

      {reviews24.length === 0 ? (
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-6 text-center text-sm text-slate-400">
          No predictions in the last 24 hours.{" "}
          <Link to="/predict" className="text-sky-400 hover:underline">Run your first analysis</Link>
        </div>
      ) : (
        <div className="space-y-2">
          {reviews24.map((r) => {
            const key = outcomeKey(r);
            const open = expandedId === r.id;
            const chart = chartCache[r.id];
            return (
              <div key={r.id} className="rounded-lg border border-slate-700 bg-slate-900">
                <button
                  type="button"
                  onClick={() => toggleChart(r.id)}
                  className="flex w-full flex-wrap items-center justify-between gap-2 p-4 text-left text-sm hover:bg-slate-800/50"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{r.symbol}</span>
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-xs">{r.predicted_action}</span>
                    <span className="text-slate-400">{(r.predicted_confidence * 100).toFixed(0)}%</span>
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        key === "correct"
                          ? "bg-green-950 text-green-400"
                          : key === "incorrect"
                            ? "bg-red-950 text-red-400"
                            : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {outcomeLabel(r)}
                    </span>
                    {r.conflict && (
                      <span className="rounded bg-amber-950 px-2 py-0.5 text-xs text-amber-400">Conflict</span>
                    )}
                  </div>
                  <span className="text-xs text-slate-500">
                    {r.predicted_at ? new Date(r.predicted_at).toLocaleString() : "—"}
                    {open ? " ▲" : " ▼"}
                  </span>
                </button>
                {open && (
                  <div className="border-t border-slate-700 px-4 pb-4">
                    <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3">
                      <span>Entry: {r.entry_price?.toFixed?.(5) ?? r.entry_price ?? "—"}</span>
                      <span>Target: {r.target_price?.toFixed?.(5) ?? "—"}</span>
                      <span>Market: {r.actual_direction ?? "—"} {r.market_outcome ? `(${r.market_outcome})` : ""}</span>
                    </div>
                    {chartLoading === r.id && <p className="py-4 text-sm text-slate-500">Loading 60min chart…</p>}
                    {chart && (
                      <PredictionHistoryChart
                        candles={chart.candles}
                        entry={chart.entry_price}
                        target={chart.target_price}
                        invalidation={chart.invalidation_price}
                        actual={chart.actual_price}
                        predictedAt={chart.predicted_at}
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, accent = "text-white" }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  );
}
