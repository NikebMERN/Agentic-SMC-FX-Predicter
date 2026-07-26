import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const GROUPS = [
  ["market", "Market"],
  ["pairs", "Currency Pair"],
  ["strategies", "Strategy"],
  ["timeframes", "Timeframe"],
];

function MetricTable({ title, rows }) {
  return (
    <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
      <h2 className="mb-3 font-medium">{title} performance</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-[#8b949e]">
            <tr><th className="pb-2">Name</th><th>Signals</th><th>Win rate</th><th>Profit factor</th><th>Expectancy</th><th>Sharpe</th><th>Max DD</th></tr>
          </thead>
          <tbody>
            {(rows || []).map((row) => (
              <tr key={row.name} className="border-t border-[#30363d]">
                <td className="py-2 font-medium">{row.name}</td>
                <td>{row.signals}</td>
                <td>{row.win_rate == null ? "—" : `${(row.win_rate * 100).toFixed(1)}%`}</td>
                <td>{row.profit_factor?.toFixed?.(2) ?? "—"}</td>
                <td>{row.expectancy?.toFixed?.(3) ?? "—"} R</td>
                <td>{row.sharpe_ratio?.toFixed?.(2) ?? "—"}</td>
                <td>{row.max_drawdown?.toFixed?.(2) ?? "—"} R</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function PerformancePage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/performance/overview").then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <PageAlerts error={error} />;
  if (!data) return <p className="text-[#8b949e]">Loading…</p>;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Performance Intelligence</h1>
        <p className="text-sm text-[#8b949e]">Verified outcomes grouped across institutional execution dimensions.</p>
      </div>
      {GROUPS.map(([key, title]) => <MetricTable key={key} title={title} rows={data[key]} />)}
    </div>
  );
}
