import MarketChart from "./MarketChart.jsx";

function shortTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(5, 16);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function PredictionHistoryChart({ candles, entry, target, invalidation, actual, predictedAt }) {
  if (!candles?.length) {
    return <p className="py-6 text-center text-sm text-slate-500">No 60min candle data for this prediction.</p>;
  }

  const lines = [
    entry > 0 && { price: entry, color: "#22c55e", title: "Entry" },
    target > 0 && { price: target, color: "#a855f7", title: "Target" },
    invalidation > 0 && { price: invalidation, color: "#ef4444", title: "Stop" },
    actual > 0 && { price: actual, color: "#fbbf24", title: "Actual" },
  ].filter(Boolean);

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-950/50 p-2">
      <p className="mb-2 text-xs text-slate-400">
        {candles.length} bars
        {predictedAt && ` · predicted ${shortTime(predictedAt)}`}
      </p>
      <MarketChart candles={candles} lines={lines} height={260} />
    </div>
  );
}
