import { Fragment, useCallback, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { usePageLoad, withNotice } from "../hooks/usePageLoad.js";
import { formatOutcomeScore, formatTimestamp } from "../utils/formatters.js";

export default function TradesPage() {
  const [trades, setTrades] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");

  const loadTrades = useCallback(async () => {
    const d = await api("/trades");
    setTrades(d.trades || []);
  }, []);

  const { loading, error, reload } = usePageLoad(loadTrades, []);

  async function closeTrade(id) {
    if (!confirm(`Force-close trade ${id}?`)) return;
    try {
      const res = await withNotice(setNotice, setActionError, () => api(`/trades/${id}/close`, { method: "POST" }));
      setNotice(`Trade ${id} closed${res?.pnl != null ? ` (PnL ${res.pnl})` : ""}`);
      await reload();
    } catch {
      /* shown in banner */
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Trades</h1>
      <p className="mb-4 text-sm text-[#8b949e]">
        Outcome score: +10 win, -5 loss, 0 breakeven — used for model feedback weighting. Click a row for details.
      </p>
      <button onClick={reload} disabled={loading} className="mb-4 rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white disabled:opacity-50">{loading ? "Loading…" : "Refresh"}</button>
      <PageAlerts error={error || actionError} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="text-left text-[#8b949e]">
            <tr>
              <th className="p-2">ID</th><th>User</th><th>Symbol</th><th>Side</th><th>Status</th>
              <th>Entry</th><th>PnL</th><th>Score</th><th>Conf</th><th>Opened</th><th></th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && !loading && (
              <tr><td colSpan={11} className="p-4 text-center text-[#8b949e]">No trades yet</td></tr>
            )}
            {trades.map((t) => (
              <Fragment key={t.id}>
                <tr
                  className="cursor-pointer border-t border-[#30363d] hover:bg-[#161b22]/80"
                  onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                >
                  <td className="p-2">{t.id}</td><td>{t.user_id}</td><td>{t.symbol}</td><td>{t.side}</td>
                  <td>{t.status}</td><td>{t.entry_price}</td><td>{t.pnl ?? "-"}</td>
                  <td>{t.outcome_score_label ?? formatOutcomeScore(t.outcome_score)}</td>
                  <td>{t.confidence != null ? `${(t.confidence * 100).toFixed(0)}%` : "-"}</td>
                  <td className="text-xs text-[#8b949e]">{formatTimestamp(t.opened_at)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {t.status === "OPEN" && (
                      <button type="button" onClick={() => closeTrade(t.id)} className="text-xs text-[#d29922]">Close</button>
                    )}
                  </td>
                </tr>
                {expanded === t.id && (
                  <tr className="border-t border-[#30363d] bg-[#0d1117]">
                    <td colSpan={11} className="p-4 text-sm text-[#8b949e]">
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        <span>Stop loss: {t.stop_loss ?? "—"}</span>
                        <span>Take profit: {t.take_profit ?? "—"}</span>
                        <span>Lot size: {t.lot_size ?? "—"}</span>
                        <span>Opened: {formatTimestamp(t.opened_at)}</span>
                        <span>Closed: {formatTimestamp(t.closed_at)}</span>
                        <span>PnL: {t.pnl ?? "—"}</span>
                        <span className="sm:col-span-2 lg:col-span-3">
                          {t.scoring_help || "Outcome score is set when the trade closes."}
                        </span>
                      </div>
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
