import { tradeEntryLabel } from "../utils/feedbackLabels.js";

const TRADE_ENTRY_OPTIONS = [
  {
    value: "ENTERED",
    label: "Accept — I entered this trade",
    className: "border-green-600/70 bg-green-950/30 text-green-300 hover:bg-green-950/50",
  },
  {
    value: "DID_NOT_TAKE",
    label: "Reject — I did not take it",
    className: "border-slate-600 text-slate-300 hover:bg-slate-800",
  },
];

const _TRADE_ENTRY_LABELS = {
  ENTERED: "Accepted — entered trade",
  DID_NOT_TAKE: "Rejected — did not take",
};

export default function TradeEntryFeedback({ review, busy, onSubmit, compact = false }) {
  if (!review?.can_record_trade_entry) {
    if (review?.user_trade_entry) {
      return (
        <p className={`text-slate-400 ${compact ? "text-xs" : "text-sm"}`}>
          Trade entry: {tradeEntryLabel(review.user_trade_entry)}
        </p>
      );
    }
    return null;
  }

  return (
    <div className={`rounded-lg border border-sky-800/40 bg-sky-950/20 ${compact ? "mt-2 p-2" : "mt-3 p-3"}`}>
      <p className={`font-medium text-sky-200 ${compact ? "mb-1 text-xs" : "mb-2 text-sm"}`}>
        Did you take this trade?
      </p>
      {!compact && (
        <p className="mb-2 text-xs text-slate-400">
          Optional — tell us if you acted on this signal right after the analysis.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {TRADE_ENTRY_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={busy}
            onClick={() => onSubmit(review.id, opt.value)}
            className={`rounded border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${opt.className}`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
