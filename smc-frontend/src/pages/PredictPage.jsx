import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import ApprovedRoute from "../components/ApprovedRoute.jsx";

const INTERVALS = ["5min", "15min", "30min", "60min"];
const HORIZONS = [
  { value: "scalping", label: "Scalping (~1h)" },
  { value: "intraday", label: "Intraday (~4h)" },
  { value: "swing", label: "Swing (~24h)" },
];
const STRATEGIES = [
  { value: "both", label: "SMC + ICT (combined)" },
  { value: "smc", label: "SMC only" },
  { value: "ict", label: "ICT only" },
];

const ACTION_COLOR = {
  BUY_BIAS: "text-green-400",
  SELL_BIAS: "text-red-400",
  WAIT_FOR_CONFIRMATION: "text-yellow-400",
  NO_TRADE: "text-amber-400",
};

export default function PredictPage() {
  const { symbol: routeSymbol } = useParams();
  const navigate = useNavigate();
  const { setProfile } = useAuth();
  const [pairs, setPairs] = useState(["EURUSD"]);
  const [symbol, setSymbol] = useState(routeSymbol?.toUpperCase() || "EURUSD");
  const [interval, setInterval] = useState("60min");
  const [horizon, setHorizon] = useState("intraday");
  const [pullLatest, setPullLatest] = useState(true);
  const [strategy, setStrategy] = useState("both");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [disclosureAccepted, setDisclosureAccepted] = useState(true);
  const [showDisclosure, setShowDisclosure] = useState(false);
  const [disclaimer, setDisclaimer] = useState("Probabilistic signal — not financial advice.");

  useEffect(() => {
    if (routeSymbol) setSymbol(routeSymbol.toUpperCase());
  }, [routeSymbol]);

  useEffect(() => {
    api("/pairs")
      .then((d) => {
        const list = d.pairs || ["EURUSD"];
        setPairs(list);
        if (d.interval) setInterval(d.interval);
      })
      .catch(() => {});
    api("/me")
      .then((me) => {
        setDisclosureAccepted(Boolean(me.risk_disclosure_accepted));
        if (me.disclaimer) setDisclaimer(me.disclaimer);
        if (!me.risk_disclosure_accepted) setShowDisclosure(true);
      })
      .catch(() => {});
  }, []);

  async function acceptDisclosure() {
    await api("/me/accept-disclosure", { method: "POST" });
    setDisclosureAccepted(true);
    setShowDisclosure(false);
  }

  async function run() {
    if (!disclosureAccepted) {
      setShowDisclosure(true);
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await api("/analyze", {
        method: "POST",
        body: JSON.stringify({ symbol, interval, horizon, fetch: pullLatest, strategy }),
      });
      setResult(r);
      if (r.quota) {
        const me = await api("/me");
        setProfile(me);
      }
    } catch (err) {
      if (err.status === 401) {
        setError("Session expired — please sign in again.");
        navigate("/login", { state: { from: `/predict/${symbol}` } });
      } else if (err.code === "disclosure_required") {
        setShowDisclosure(true);
        setError(err.message);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  const d = result?.decision;
  const scores = d?.component_scores || {};

  return (
    <ApprovedRoute>
      {showDisclosure && !disclosureAccepted && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="max-w-md rounded-lg border border-slate-600 bg-slate-900 p-6">
            <h2 className="mb-2 text-lg font-semibold">Risk disclosure</h2>
            <p className="mb-4 text-sm text-slate-300">{disclaimer}</p>
            <button onClick={acceptDisclosure} className="rounded bg-sky-600 px-4 py-2 text-sm text-white">
              I understand — continue
            </button>
          </div>
        </div>
      )}
      <div className="mx-auto max-w-4xl px-4 py-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold">Run prediction — {symbol}</h1>
          <Link to="/" className="text-sm text-sky-400 hover:underline">
            ← All pairs
          </Link>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              navigate(`/predict/${e.target.value}`);
            }}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm"
          >
            {pairs.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select value={interval} onChange={(e) => setInterval(e.target.value)} className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm">
            {INTERVALS.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
          <select value={horizon} onChange={(e) => setHorizon(e.target.value)} className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm">
            {HORIZONS.map((h) => (
              <option key={h.value} value={h.value}>{h.label}</option>
            ))}
          </select>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm"
          >
            {STRATEGIES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-sm text-slate-400">
            <input type="checkbox" checked={pullLatest} onChange={(e) => setPullLatest(e.target.checked)} />
            Pull latest data
          </label>
          <button onClick={run} disabled={loading} className="rounded bg-sky-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {loading ? "Working…" : "Analyze"}
          </button>
        </div>
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
        {result?.quota && <p className="mb-3 text-sm text-slate-400">{result.quota}</p>}
        {d && (
          <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900 p-4">
            <p className="text-lg">
              {result.symbol} →{" "}
              <strong className={ACTION_COLOR[d.action] || "text-slate-200"}>
                {d.action}
              </strong>{" "}
              ({(d.confidence * 100).toFixed(0)}%)
            </p>
            <p className="text-xs text-slate-500">Horizon: {horizon}</p>
            {d.entry != null && (
              <p className="text-sm text-slate-400">
                Entry {d.entry} · Invalidation {d.invalidation_price ?? d.stop_loss} · Target {d.target_liquidity ?? d.take_profit}
              </p>
            )}
            {Object.keys(scores).length > 0 && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {Object.entries(scores).map(([k, v]) => (
                  <div key={k} className="text-xs">
                    <div className="mb-1 flex justify-between text-slate-400">
                      <span>{k.replace(/_/g, " ")}</span>
                      <span>{v}</span>
                    </div>
                    <div className="h-1.5 rounded bg-slate-800">
                      <div className="h-1.5 rounded bg-sky-600" style={{ width: `${v}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <ul className="mt-3 space-y-1 text-sm text-slate-400">
              {d.reasoning?.map((r, i) => (
                <li key={i}>• {r}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-amber-200/80">{d.disclaimer || disclaimer}</p>
          </div>
        )}
        <p className="text-sm text-slate-500">
          Results are tracked in{" "}
          <Link to="/feedback" className="text-sky-400 hover:underline">My feedback</Link> after the horizon window.
        </p>
      </div>
    </ApprovedRoute>
  );
}
