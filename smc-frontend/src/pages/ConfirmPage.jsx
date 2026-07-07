import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import ApprovedRoute from "../components/ApprovedRoute.jsx";
import MarketChart from "../components/MarketChart.jsx";
import TradeEntryFeedback, { isTradeAction } from "../components/TradeEntryFeedback.jsx";

const ACTION_COLOR = {
  BUY_BIAS: "text-green-400",
  SELL_BIAS: "text-red-400",
  WAIT_FOR_CONFIRMATION: "text-yellow-400",
  NO_TRADE: "text-amber-400",
};

function DecisionSummary({ result, waitReason, confirmationReason }) {
  const d = result?.decision;
  const pred = result?.prediction;
  const mtfCtx = result?.mtf_context;
  if (!d) return null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
      {waitReason && (
        <div className="mb-3 rounded border border-yellow-900/50 bg-yellow-950/20 p-3">
          <p className="text-xs uppercase tracking-wide text-yellow-400">You were waiting for</p>
          <p className="mt-1 text-sm text-yellow-100">{waitReason}</p>
        </div>
      )}
      {confirmationReason && (
        <div className="mb-3 rounded border border-green-900/50 bg-green-950/20 p-3">
          <p className="text-xs uppercase tracking-wide text-green-400">Confirmation</p>
          <p className="mt-1 text-sm text-green-100">{confirmationReason}</p>
        </div>
      )}
      <p className="text-lg">
        {result.symbol} →{" "}
        <strong className={ACTION_COLOR[d.action] || "text-slate-200"}>{d.action}</strong>{" "}
        ({(d.confidence * 100).toFixed(0)}%)
      </p>
      {pred?.entryPlan && (
        <p className="mt-1 text-xs text-slate-400">
          Invalidation: {pred.entryPlan.invalidationPrice ?? "—"} · Target: {pred.entryPlan.targetLiquidityPrice ?? "—"}
        </p>
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
          </div>
          <div className="rounded border border-green-900/60 bg-green-950/30 p-3 text-center">
            <div className="text-xs uppercase tracking-wide text-green-400">Take Profit</div>
            <div className="mt-1 text-base font-semibold text-green-300">
              {d.target_liquidity ?? d.take_profit}
            </div>
          </div>
        </div>
      )}
      {result?.candle_snapshot?.length > 0 && (
        <div className="mt-3 rounded border border-slate-700 bg-slate-950/60 p-3">
          <MarketChart
            pair={result.symbol}
            candles={result.candle_snapshot}
            height={280}
            lines={[
              d.entry > 0 && { price: d.entry, color: "#38bdf8", title: "Entry" },
              (d.invalidation_price ?? d.stop_loss) > 0 && {
                price: d.invalidation_price ?? d.stop_loss,
                color: "#ef4444",
                title: "Stop",
              },
              (d.target_liquidity ?? d.take_profit) > 0 && {
                price: d.target_liquidity ?? d.take_profit,
                color: "#22c55e",
                title: "Target",
              },
            ].filter(Boolean)}
          />
        </div>
      )}
      {mtfCtx?.notes?.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-slate-400">
          {mtfCtx.notes.slice(0, 3).map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ConfirmPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { setProfile } = useAuth();
  const [watch, setWatch] = useState(null);
  const [step, setStep] = useState("prompt");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tradeError, setTradeError] = useState("");
  const [result, setResult] = useState(null);
  const [tradeEntryReview, setTradeEntryReview] = useState(null);
  const [tradeEntryBusy, setTradeEntryBusy] = useState(false);

  const loadWatch = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api(`/my/confirmations/${id}`);
      setWatch(data);
      if (data.status !== "confirmed") {
        setStep("waiting");
      } else if (data.review?.id) {
        setStep("ready");
        setResult(data.snapshot || data.analyze_result || null);
        if (isTradeAction(data.review.predicted_action)) {
          setTradeEntryReview({
            id: data.review.id,
            can_record_trade_entry: data.review.can_record_trade_entry,
            user_trade_entry: data.review.user_trade_entry,
          });
        }
      }
    } catch (err) {
      setError(err.message || "Could not load confirmation.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadWatch();
  }, [loadWatch]);

  async function skipAnalyze() {
    setBusy(true);
    setError("");
    try {
      const data = await api(`/my/confirmations/${id}/materialize`, { method: "POST" });
      setWatch(data);
      setResult(data.snapshot);
      setStep("ready");
      if (data.review && isTradeAction(data.review.predicted_action)) {
        setTradeEntryReview({
          id: data.review.id,
          can_record_trade_entry: data.review.can_record_trade_entry,
          user_trade_entry: data.review.user_trade_entry,
        });
      }
    } catch (err) {
      setError(err.message || "Could not load setup.");
    } finally {
      setBusy(false);
    }
  }

  async function runFreshAnalyze() {
    setBusy(true);
    setError("");
    try {
      const data = await api(`/my/confirmations/${id}/analyze`, { method: "POST" });
      setWatch(data);
      setResult(data.analyze_result || data.snapshot);
      setStep("ready");
      if (data.review && isTradeAction(data.review.predicted_action)) {
        setTradeEntryReview({
          id: data.review.id,
          can_record_trade_entry: data.review.can_record_trade_entry,
          user_trade_entry: data.review.user_trade_entry,
        });
      }
      if (data.quota) {
        const me = await api("/me");
        setProfile(me);
      }
    } catch (err) {
      if (err.body?.code === "disclosure_required") {
        navigate("/predict", { state: { fromConfirm: id } });
      } else {
        setError(err.message || "Analysis failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitTradeEntry(reviewId, feedback) {
    setTradeEntryBusy(true);
    setTradeError("");
    try {
      await api(`/my/reviews/${reviewId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback, kind: "trade_entry" }),
      });
      setTradeEntryReview((prev) =>
        prev ? { ...prev, can_record_trade_entry: false, user_trade_entry: feedback } : prev,
      );
    } catch (err) {
      setTradeError(err.message || "Could not save your response.");
    } finally {
      setTradeEntryBusy(false);
    }
  }

  return (
    <ApprovedRoute>
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-100">Setup confirmation</h1>
          <Link to="/predict" className="text-sm text-sky-400 hover:underline">
            Back to Predict
          </Link>
        </div>

        {loading && <p className="text-slate-400">Loading…</p>}
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}

        {!loading && watch?.status === "waiting" && (
          <div className="rounded-lg border border-yellow-800/50 bg-yellow-950/20 p-4">
            <p className="font-medium text-yellow-200">
              {watch.symbol} is still waiting for confirmation
            </p>
            <p className="mt-2 text-sm text-slate-300">{watch.wait_reason}</p>
            <p className="mt-3 text-xs text-slate-500">
              We will notify you on web and Telegram when the setup confirms.
            </p>
          </div>
        )}

        {!loading && watch?.status === "confirmed" && step === "prompt" && (
          <div className="rounded-lg border border-sky-800/50 bg-sky-950/20 p-4">
            <p className="font-medium text-sky-200">
              {watch.symbol} {watch.confirmed_action} — ready to enter
            </p>
            <p className="mt-2 text-sm text-slate-300">
              You were waiting for: {watch.wait_reason}
            </p>
            <p className="mt-1 text-sm text-green-300">{watch.confirmation_reason}</p>
            <p className="mt-4 text-sm text-slate-400">
              Would you like a fresh analysis before you decide whether to enter?
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={runFreshAnalyze}
                className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {busy ? "Analyzing…" : "Yes — run fresh analysis"}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={skipAnalyze}
                className="rounded border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                No — show confirmed setup
              </button>
            </div>
          </div>
        )}

        {!loading && step === "ready" && result && (
          <>
            <DecisionSummary
              result={result}
              waitReason={watch?.wait_reason}
              confirmationReason={watch?.confirmation_reason}
            />
            {tradeError && <p className="mt-2 text-sm text-red-400">{tradeError}</p>}
            {tradeEntryReview && (
              <TradeEntryFeedback
                review={tradeEntryReview}
                busy={tradeEntryBusy}
                onSubmit={submitTradeEntry}
              />
            )}
          </>
        )}
      </div>
    </ApprovedRoute>
  );
}
