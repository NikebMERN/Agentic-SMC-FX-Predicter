const SETTING_LABELS = {
  supported_pairs: "Supported currency pairs",
  min_final_confidence: "Minimum blended confidence",
  broadcast_signals: "Broadcast signals to Telegram",
  predictions_enabled: "Predictions enabled",
  disabled_pairs: "Disabled pairs",
};

export function formatSettingKey(key) {
  return SETTING_LABELS[key] || key.replace(/_/g, " ");
}

export function formatSettingValue(key, value) {
  if (key === "min_final_confidence") {
    const n = Number(value);
    return Number.isFinite(n) ? `${(n * 100).toFixed(0)}%` : String(value);
  }
  if (key === "broadcast_signals" || key === "predictions_enabled") {
    return value === true || value === "true" ? "Yes" : "No";
  }
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "—");
}

export function formatServerConfig(cfg) {
  if (!cfg) return [];
  return [
    { label: "Candle interval", value: cfg.interval || "—" },
    { label: "Data provider (configured)", value: cfg.data_provider || "auto" },
    { label: "Active provider", value: cfg.active_provider || "none" },
    { label: "OANDA environment", value: cfg.oanda_env || "—" },
    { label: "OANDA API key", value: cfg.oanda_key_set ? "Set" : "Not set" },
    { label: "Alpha Vantage key", value: cfg.alpha_vantage_key_set ? "Set" : "Not set" },
    { label: "Telegram bot token", value: cfg.telegram_bot_token_set ? "Set" : "Not set" },
    { label: "Fetch cooldown", value: `${cfg.fetch_cooldown_minutes ?? "—"} min` },
    { label: "CORS origins", value: cfg.cors_origins || "—" },
    { label: "Data directory", value: cfg.data_dir || "—" },
    { label: "Model directory", value: cfg.model_dir || "—" },
  ];
}

export function formatOutcomeScore(score) {
  if (score === 10) return "Win +10";
  if (score === -5) return "Loss -5";
  if (score === 0) return "Neutral 0";
  return "—";
}

export function formatReviewStatus(status) {
  const map = {
    pending: "Pending evaluation",
    awaiting_feedback: "Awaiting user feedback",
    evaluated: "Evaluated — needs action",
    retrain_done: "Retrain completed",
    dismissed: "Dismissed",
    verification_failed: "Verification failed",
  };
  return map[status] || status || "—";
}

export function formatFeedbackLabel(feedback) {
  const map = {
    SUCCESSFUL: "Successful",
    FAILED: "Failed",
    DID_NOT_TAKE: "Did not take",
    UNCLEAR: "Unclear",
  };
  return map[feedback] || feedback || "—";
}

export function formatMarketDirection(dir) {
  const map = { UP: "Up", DOWN: "Down", SIDEWAYS: "Sideways" };
  return map[dir] || dir || "—";
}

export function formatAuditDetail(raw) {
  if (!raw) return "";
  let data = raw;
  if (typeof raw === "string") {
    try {
      data = JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  if (typeof data !== "object") return String(data);

  const parts = [];
  if (data.role) parts.push(`role set to ${data.role}`);
  if (data.signals_remaining != null) parts.push(`quota → ${data.signals_remaining}`);
  if (data.banned != null) parts.push(data.banned ? "banned" : "unbanned");
  if (data.admin_status) parts.push(`status → ${data.admin_status}`);
  if (data.symbol) parts.push(`symbol ${data.symbol}`);
  if (data.promote != null) parts.push(data.promote ? "promoted" : "not promoted");
  if (data.pnl != null) parts.push(`PnL ${data.pnl}`);
  if (data.count != null) parts.push(`${data.count} records`);
  if (parts.length) return parts.join(" · ");
  return Object.entries(data)
    .map(([k, v]) => `${formatSettingKey(k)}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(" · ");
}

export function formatTimestamp(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso).slice(0, 19);
  }
}
