import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

function Badge({ ok, children, warn }) {
  const cls = ok
    ? "bg-[#1a3a24] text-[#3fb950]"
    : warn
      ? "bg-[#3a2d12] text-[#d29922]"
      : "bg-[#3d1d20] text-[#f85149]";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${cls}`}>
      {children}
    </span>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [showAllPairs, setShowAllPairs] = useState(true);
  const [showAllBacktests, setShowAllBacktests] = useState(false);

  useEffect(() => {
    Promise.all([api("/overview"), api("/analytics").catch(() => null)])
      .then(([overview, an]) => {
        setData(overview);
        setAnalytics(an);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <PageAlerts error={error} />;
  if (!data) return <p className="text-[#8b949e]">Loading…</p>;

  const s = data.stats;
  const h = data.health;
  const anyKeySet = h.any_api_key_set || h.oanda_key_set || h.alpha_vantage_key_set;
  const liveOk = h.live_fetch_available;
  const cacheCount = h.cache_pairs_count ?? h.cached_csv_files ?? 0;
  const cacheOk = cacheCount > 0;
  const dataReady = h.data_ready ?? (liveOk || anyKeySet || cacheOk);
  let dataKeyLabel = "No data API key or cache";
  let dataKeyOk = dataReady;
  let dataKeyWarn = false;
  if (liveOk) {
    dataKeyLabel = h.active_provider === "oanda" ? "OANDA live" : h.active_provider === "alphavantage" ? "Alpha Vantage live" : "Live data ready";
  } else if (anyKeySet && !liveOk) {
    dataKeyLabel = `API key set (${h.data_provider_config || "auto"}) — check DATA_PROVIDER`;
    dataKeyWarn = true;
    dataKeyOk = true;
  } else if (cacheOk) {
    dataKeyLabel = `Cached CSV (${cacheCount} pairs)`;
    dataKeyWarn = !anyKeySet;
  }
  const rows = showAllPairs ? data.data_status : data.data_status.slice(0, 12);
  const bt = data.latest_backtest;
  const btSummary = bt?.summary || (bt?.symbol ? bt : null);
  const btPairs = bt?.pairs || (bt?.symbol ? [bt] : []);

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold">Dashboard</h1>
      <p className="mb-4 text-xs text-[#8b949e]">Server {data.server_time} · interval {data.interval}</p>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {[["Users", s.users], ["Accounts", s.accounts], ["Signals", s.signals], ["Trades", s.trades], ["Open trades", s.open_trades], ["Models", h.models_on_disk]].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-2xl font-bold">{v}</div>
            <div className="text-xs text-[#8b949e]">{k}</div>
          </div>
        ))}
      </div>
      <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <h2 className="mb-3 font-medium">System health</h2>
        <div className="flex flex-wrap gap-2">
          <Badge ok={h.database}>{h.database ? "DB connected" : "DB down"}</Badge>
          <Badge ok>{`Provider: ${h.data_provider_config || "auto"} → ${h.active_provider || "none"}`}</Badge>
          <Badge ok={dataKeyOk} warn={dataKeyWarn}>{dataKeyLabel}</Badge>
          <Badge ok={h.telegram_bot}>{h.telegram_bot ? "Telegram configured" : "Telegram not set"}</Badge>
          {h.refresh_running && <span className="rounded-full bg-[#3a2d12] px-2 py-0.5 text-xs text-[#d29922]">Refresh running</span>}
          {h.log_file_kb != null && <span className="rounded-full bg-[#21262d] px-2 py-0.5 text-xs text-[#8b949e]">Log {h.log_file_kb} KB</span>}
        </div>
      </div>
      {btSummary && (
        <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-medium">Latest backtest — {btSummary.symbol}</h2>
            {btPairs.length > 1 && (
              <button type="button" onClick={() => setShowAllBacktests((v) => !v)} className="text-xs text-[#2f81f7]">
                {showAllBacktests ? "Hide pairs" : `All ${btPairs.length} pairs`}
              </button>
            )}
          </div>
          <p className="text-sm text-[#8b949e]">
            Win rate {((btSummary.win_rate ?? 0) * 100).toFixed(1)}% · {btSummary.trades ?? 0} trades · avg RR {btSummary.avg_rr ?? "—"}
            {btSummary.generated_at && ` · ${String(btSummary.generated_at).slice(0, 19)}`}
          </p>
          {showAllBacktests && btPairs.length > 1 && (
            <table className="mt-3 w-full text-sm">
              <thead><tr className="text-left text-[#8b949e]"><th className="pb-1">Pair</th><th>Win rate</th><th>Trades</th><th>Avg RR</th></tr></thead>
              <tbody>
                {btPairs.map((p) => (
                  <tr key={p.symbol} className="border-t border-[#30363d]">
                    <td className="py-1">{p.symbol}</td>
                    <td>{p.win_rate != null ? `${(p.win_rate * 100).toFixed(1)}%` : "—"}</td>
                    <td>{p.trades ?? "—"}</td>
                    <td>{p.avg_rr ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {analytics && (
        <div className="mb-6 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-2xl font-bold">{analytics.conflict_count ?? 0}</div>
            <div className="text-xs text-[#8b949e]">User/market conflicts</div>
          </div>
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-2xl font-bold">{analytics.verification_failure_count ?? 0}</div>
            <div className="text-xs text-[#8b949e]">Verification failures</div>
          </div>
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <div className="text-sm font-medium">Calibration</div>
            <div className="mt-1 text-xs text-[#8b949e]">
              {Object.entries(analytics.calibration || {}).map(([k, v]) => (
                <div key={k}>{k}: {v.accuracy != null ? `${(v.accuracy * 100).toFixed(0)}%` : "—"} ({v.total})</div>
              ))}
            </div>
          </div>
        </div>
      )}
      <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">Data freshness ({data.data_status.length} pairs)</h2>
          {data.data_status.length > 12 && (
            <button type="button" onClick={() => setShowAllPairs((v) => !v)} className="text-xs text-[#2f81f7]">
              {showAllPairs ? "Show less" : "Show all"}
            </button>
          )}
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[#8b949e]">
              <th className="pb-2">Pair</th>
              <th>CSV</th>
              <th>Age (min)</th>
              <th>Size (KB)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.symbol} className="border-t border-[#30363d]">
                <td className="py-2">{x.symbol}</td>
                <td>{x.exists ? <Badge ok>cached</Badge> : <Badge ok={false}>missing</Badge>}</td>
                <td>{x.age_minutes ?? "-"}</td>
                <td>{x.size_kb ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
