const OUTCOME_OPTIONS = [
  { value: "SUCCESSFUL", label: "Successful", className: "border-green-600/70 bg-green-950/30 text-green-300 hover:bg-green-950/50" },
  { value: "FAILED", label: "Failed", className: "border-red-700/60 bg-red-950/30 text-red-300 hover:bg-red-950/50" },
  { value: "DID_NOT_TAKE", label: "Didn't take", className: "border-slate-600 text-slate-300 hover:bg-slate-800" },
];

export function outcomeLabel(feedback) {
  const map = {
    SUCCESSFUL: "Successful",
    FAILED: "Failed",
    DID_NOT_TAKE: "Didn't take",
    UNCLEAR: "Unclear",
  };
  return map[feedback] || feedback;
}

export default function OutcomeFeedback({ review, busy, onSubmit, compact = false }) {
  if (!review?.can_record_outcome) {
    if (review?.user_feedback) {
      return (
        <p className={`text-slate-400 ${compact ? "text-xs" : "text-sm"}`}>
          Your outcome: {outcomeLabel(review.user_feedback)}
        </p>
      );
    }
    if (review?.user_trade_entry === "DID_NOT_TAKE") {
      return (
        <p className={`text-slate-400 ${compact ? "text-xs" : "text-sm"}`}>
          You marked this signal as not taken.
        </p>
      );
    }
    return null;
  }

  return (
    <div className={`rounded-lg border border-amber-800/40 bg-amber-950/20 ${compact ? "mt-2 p-2" : "mt-3 p-3"}`}>
      <p className={`font-medium text-amber-200 ${compact ? "mb-1 text-xs" : "mb-2 text-sm"}`}>
        How did this trade go?
      </p>
      {!compact && (
        <p className="mb-2 text-xs text-slate-400">
          Optional — rate the result when you’re ready. We cross-check with market data when available.
        </p>
      )}
      {review.user_trade_entry === "ENTERED" && (
        <p className="mb-2 text-xs text-sky-400">You entered this trade.</p>
      )}
      <div className="flex flex-wrap gap-2">
        {OUTCOME_OPTIONS.map((opt) => (
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
