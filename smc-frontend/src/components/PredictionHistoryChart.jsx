import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

  const data = candles.map((c) => ({
    time: shortTime(c.time),
    close: c.close,
    high: c.high,
    low: c.low,
  }));

  const prices = data.flatMap((d) => [d.close, d.high, d.low]);
  if (entry) prices.push(entry);
  if (target) prices.push(target);
  if (invalidation) prices.push(invalidation);
  if (actual) prices.push(actual);
  const min = Math.min(...prices) * 0.9998;
  const max = Math.max(...prices) * 1.0002;

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-950/50 p-2">
      <p className="mb-2 text-xs text-slate-400">
        60min candles ({candles.length} bars)
        {predictedAt && ` · predicted ${shortTime(predictedAt)}`}
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="time" tick={{ fill: "#94a3b8", fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis domain={[min, max]} tick={{ fill: "#94a3b8", fontSize: 10 }} width={72} tickFormatter={(v) => v.toFixed(5)} />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            formatter={(v) => [Number(v).toFixed(5), "Close"]}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="close" name="Close (60min)" stroke="#38bdf8" dot={false} strokeWidth={2} />
          {entry > 0 && (
            <ReferenceLine y={entry} stroke="#22c55e" strokeDasharray="4 4" label={{ value: "Entry", fill: "#22c55e", fontSize: 10 }} />
          )}
          {target > 0 && (
            <ReferenceLine y={target} stroke="#a855f7" strokeDasharray="4 4" label={{ value: "Target", fill: "#a855f7", fontSize: 10 }} />
          )}
          {invalidation > 0 && (
            <ReferenceLine y={invalidation} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "Stop", fill: "#ef4444", fontSize: 10 }} />
          )}
          {actual > 0 && (
            <ReferenceLine y={actual} stroke="#fbbf24" strokeDasharray="2 2" label={{ value: "Actual", fill: "#fbbf24", fontSize: 10 }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
