import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import ApprovedRoute from "../components/ApprovedRoute.jsx";
import MarketChart from "../components/MarketChart.jsx";

const MODES = [
  { value: "mtf", label: "Multi-TF (auto by trading style)" },
  { value: "5min", label: "Single TF: 5min" },
  { value: "15min", label: "Single TF: 15min" },
  { value: "30min", label: "Single TF: 30min" },
  { value: "60min", label: "Single TF: 60min" },
];
const HORIZONS = [
  { value: "scalping", label: "Scalping (1H/4H → 15M → 5M)" },
  { value: "intraday", label: "Intraday (4H/1H → 30M/15M → 5M)" },
  { value: "swing", label: "Swing (Daily/4H → 1H → 30M/15M)" },
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
  const [mode, setMode] = useState("mtf");
  const [horizon, setHorizon] = useState("intraday");
  const [balance, setBalance] = useState("1000");
  const [riskPct, setRiskPct] = useState("1");
  const [riskAmount, setRiskAmount] = useState("");
  const [calc, setCalc] = useState(null);
  const [calcBusy, setCalcBusy] = useState(false);
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
    setCalc(null);
    try {
      const body = { symbol, horizon, fetch: pullLatest, strategy };
      if (mode === "mtf") {
        body.mtf = true;
      } else {
        body.interval = mode;
        body.mtf = false;
      }
      const r = await api("/analyze", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(r);
      if (r.calculator) setCalc(r.calculator);
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

  async function recalc() {
    if (!d?.entry) return;
    setCalcBusy(true);
    try {
      const body = {
        symbol,
        entry: d.entry,
        stop_loss: d.stop_loss,
        take_profit: d.take_profit,
        balance,
        risk_pct: riskPct,
      };
      if (riskAmount !== "" && Number(riskAmount) > 0) body.risk_amount = riskAmount;
      const r = await api("/calculator", { method: "POST", body: JSON.stringify(body) });
      setCalc(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setCalcBusy(false);
    }
  }

  const d = result?.decision;
  const pred = result?.prediction;
  const scores = d?.component_scores || {};
  const mtfCtx = result?.mtf;

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
          <select value={mode} onChange={(e) => setMode(e.target.value)} className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm">
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
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
            <p className="text-xs text-slate-500">
              Trading style: {horizon}
              {pred?.score != null && ` · Score ${pred.score}/100`}
              {pred?.higherTimeframeBias && ` · HTF ${pred.higherTimeframeBias}`}
            </p>
            {mtfCtx?.timeframes_used?.length > 0 && (
              <p className="text-xs text-slate-500">Timeframes: {mtfCtx.timeframes_used.join(" → ")}</p>
            )}
            {pred?.entryPlan && (
              <p className="mt-1 text-xs text-slate-400">
                Invalidation: {pred.entryPlan.invalidationPrice ?? "—"} · Target: {pred.entryPlan.targetLiquidityPrice ?? "—"}
              </p>
            )}
            {pred?.invalidReasons?.length > 0 && (
              <ul className="mt-2 list-inside list-disc text-xs text-amber-400/90">
                {pred.invalidReasons.slice(0, 4).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
            {d.entry != null && (
              <div className="mt-3 grid grid-cols-3 gap-2">
                <div className="rounded border border-slate-700 bg-slate-950 p-3 text-center">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Entry</div>
                  <div className="mt-1 text-base font-semibold text-slate-100">{d.entry}</div>
                </div>
                <div className="rounded border border-red-900/60 bg-red-950/30 p-3 text-center">
                  <div className="text-xs uppercase tracking-wide text-red-400">Stop Loss</div>
                  <div className="mt-1 text-base font-semibold text-red-300">
                    {d.invalidation_price ?? d.stop_loss}
                  </div>
                  {d.sl_pips != null && (
                    <div className="text-xs text-red-400/80">{d.sl_pips} pips · {d.sl_pct}%</div>
                  )}
                </div>
                <div className="rounded border border-green-900/60 bg-green-950/30 p-3 text-center">
                  <div className="text-xs uppercase tracking-wide text-green-400">Take Profit</div>
                  <div className="mt-1 text-base font-semibold text-green-300">
                    {d.target_liquidity ?? d.take_profit}
                  </div>
                  {d.tp_pips != null && (
                    <div className="text-xs text-green-400/80">{d.tp_pips} pips · {d.tp_pct}%</div>
                  )}
                </div>
              </div>
            )}
            {d.risk_reward != null && (
              <p className="mt-2 text-center text-sm text-slate-400">
                Risk/Reward <span className="font-semibold text-slate-200">1 : {d.risk_reward}</span>
                {d.stop_basis === "percent_cap" && " · stop capped at the configured max distance"}
              </p>
            )}
            {result?.candle_snapshot?.length > 0 && (
              <div className="mt-3 rounded border border-slate-700 bg-slate-950/60 p-3">
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                  {result.interval} chart — last {result.candle_snapshot.length} candles with your levels
                </div>
                <MarketChart
                  pair={result.symbol}
                  candles={result.candle_snapshot}
                  height={320}
                  lines={[
                    d.entry > 0 && { price: d.entry, color: "#38bdf8", title: "Entry" },
                    (d.invalidation_price ?? d.stop_loss) > 0 && {
                      price: d.invalidation_price ?? d.stop_loss, color: "#ef4444", title: "Stop",
                    },
                    (d.target_liquidity ?? d.take_profit) > 0 && {
                      price: d.target_liquidity ?? d.take_profit, color: "#22c55e", title: "Target",
                    },
                    mtfCtx?.liquidity_draw?.level > 0 && {
                      price: mtfCtx.liquidity_draw.level, color: "#a855f7", title: "1H liquidity draw",
                    },
                  ].filter(Boolean)}
                />
              </div>
            )}
            {mtfCtx && (
              <div className="mt-3 rounded border border-sky-900/50 bg-sky-950/20 p-3 text-sm">
                <div className="mb-1 text-xs uppercase tracking-wide text-sky-400">
                  Multi-timeframe: {mtfCtx.timeframes?.bias} bias → {mtfCtx.timeframes?.liquidity} liquidity → {mtfCtx.timeframes?.entry} entry
                </div>
                {mtfCtx.h4_bias && (
                  <p className="text-slate-300">{mtfCtx.h4_bias.reason}</p>
                )}
                {mtfCtx.h1_liquidity && (
                  <p className="text-slate-400">
                    1H external liquidity: {mtfCtx.h1_liquidity.above?.length ?? 0} unswept pool(s) above · {mtfCtx.h1_liquidity.below?.length ?? 0} below
                  </p>
                )}
                {mtfCtx.liquidity_draw && (
                  <p className="text-sky-300">
                    Draw on liquidity: {mtfCtx.liquidity_draw.level} ({mtfCtx.liquidity_draw.pips_away} pips away)
                  </p>
                )}
                {mtfCtx.notes?.map((n, i) => (
                  <p key={i} className="text-xs text-amber-300/70">{n}</p>
                ))}
              </div>
            )}
            {d.entry != null && (
              <div className="mt-3 rounded border border-slate-700 bg-slate-950 p-3">
                <div className="mb-2 flex flex-wrap items-end gap-3">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Position calculator</span>
                  <label className="text-xs text-slate-400">
                    Balance $
                    <input value={balance} onChange={(e) => setBalance(e.target.value)} type="number" min="1"
                      className="ml-1 w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm" />
                  </label>
                  <label className="text-xs text-slate-400">
                    Risk %
                    <input value={riskPct} onChange={(e) => setRiskPct(e.target.value)} type="number" step="0.1" min="0.1" max="10"
                      className="ml-1 w-16 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm" />
                  </label>
                  <label className="text-xs text-slate-400">
                    or Risk $
                    <input value={riskAmount} onChange={(e) => setRiskAmount(e.target.value)} type="number" step="1" min="0" placeholder="—"
                      className="ml-1 w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm" />
                  </label>
                  <button onClick={recalc} disabled={calcBusy}
                    className="rounded bg-slate-700 px-2 py-1 text-xs text-white disabled:opacity-50">
                    {calcBusy ? "…" : "Recalculate"}
                  </button>
                </div>
                {calc ? (
                  <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                    <div>
                      <div className="text-xs text-slate-500">Lot size</div>
                      <div className="font-semibold text-slate-100">{calc.lot_size}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Risk</div>
                      <div className="font-semibold text-red-300">${calc.risk_amount}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Reward</div>
                      <div className="font-semibold text-green-300">${calc.reward_amount}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Pip value / lot</div>
                      <div className="font-semibold text-slate-100">
                        ${calc.pip_value_per_lot_usd}{calc.approximate ? " (approx.)" : ""}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Press Recalculate to size this trade for your account.</p>
                )}
                {calc?.warning && (
                  <p className="mt-2 text-xs text-amber-300">⚠ {calc.warning}</p>
                )}
              </div>
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
