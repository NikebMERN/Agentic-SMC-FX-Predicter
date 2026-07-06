/** Helpers for nested threshold config read/write and patch diffing. */

export function cloneConfig(obj) {
  return JSON.parse(JSON.stringify(obj || {}));
}

export function getSectionValue(config, sectionId, fieldKey) {
  return config?.[sectionId]?.[fieldKey];
}

export function setSectionValue(config, sectionId, fieldKey, value) {
  const next = cloneConfig(config);
  if (!next[sectionId]) next[sectionId] = {};
  next[sectionId][fieldKey] = value;
  return next;
}

export function getNestedValue(obj, path) {
  return path.reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
}

/** Return a minimal patch containing only changed leaves. */
export function diffPatch(base, updated) {
  if (base === updated) return undefined;
  if (
    base == null ||
    updated == null ||
    typeof base !== "object" ||
    typeof updated !== "object" ||
    Array.isArray(base) ||
    Array.isArray(updated)
  ) {
    return base === updated ? undefined : updated;
  }
  const out = {};
  const keys = new Set([...Object.keys(base), ...Object.keys(updated)]);
  for (const key of keys) {
    const sub = diffPatch(base[key], updated[key]);
    if (sub !== undefined) out[key] = sub;
  }
  return Object.keys(out).length ? out : undefined;
}

export function formatMetric(value) {
  if (value == null) return "—";
  if (typeof value === "number") {
    if (value > 0 && value < 1) return `${(value * 100).toFixed(1)}%`;
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

export function formatBacktestMetrics(data) {
  if (!data || data.error) return null;
  return [
    ["Trades", data.trades],
    ["Win rate", data.win_rate != null ? `${(data.win_rate * 100).toFixed(1)}%` : "—"],
    ["Accuracy (bias)", data.accuracy != null ? `${(data.accuracy * 100).toFixed(1)}%` : "—"],
    ["NO_TRADE rate", data.no_trade_rate != null ? `${(data.no_trade_rate * 100).toFixed(1)}%` : "—"],
    ["WAIT rate", data.wait_rate != null ? `${(data.wait_rate * 100).toFixed(1)}%` : "—"],
    ["Invalidation hit rate", data.invalidation_hit_rate != null ? `${(data.invalidation_hit_rate * 100).toFixed(1)}%` : "—"],
    ["Max drawdown", data.max_drawdown_pct != null ? `${data.max_drawdown_pct}%` : "—"],
  ];
}
