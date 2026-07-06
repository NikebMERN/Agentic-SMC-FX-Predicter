import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PasswordField from "../components/PasswordField.jsx";
import PairChipList from "../components/PairChipList.jsx";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import {
  formatServerConfig,
  formatSettingKey,
  formatSettingValue,
  isPairListKey,
  parsePairList,
} from "../utils/formatters.js";

function SettingValue({ settingKey, value }) {
  if (isPairListKey(settingKey)) {
    return <PairChipList value={value} maxHeight="max-h-36" />;
  }
  return <span className="break-words">{formatSettingValue(settingKey, value)}</span>;
}

function PairTextarea({ value, onChange, placeholder, rows = 4 }) {
  const pairs = parsePairList(value);
  return (
    <div>
      <textarea
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        rows={rows}
        spellCheck={false}
        className="mb-2 w-full resize-y rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 font-mono text-xs leading-relaxed text-[#e6edf3]"
      />
      {pairs.length > 0 && (
        <div className="max-h-28 overflow-y-auto rounded border border-[#21262d] bg-[#0d1117] p-2">
          <PairChipList value={value} maxHeight="max-h-24" emptyLabel="" />
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [pairs, setPairs] = useState("");
  const [conf, setConf] = useState("0.55");
  const [slMaxPct, setSlMaxPct] = useState("0.40");
  const [tpMaxPct, setTpMaxPct] = useState("0.80");
  const [broadcast, setBroadcast] = useState(false);
  const [predictionsEnabled, setPredictionsEnabled] = useState(true);
  const [disabledPairs, setDisabledPairs] = useState("");
  const [overrides, setOverrides] = useState({});
  const [configRows, setConfigRows] = useState([]);
  const [current, setCurrent] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [thresholdSummary, setThresholdSummary] = useState(null);
  const [activePairCount, setActivePairCount] = useState(0);

  function applySettingsPayload(settings) {
    const storedPairs = settings.stored?.supported_pairs ?? settings.overrides?.supported_pairs ?? "";
    const storedDisabled = settings.stored?.disabled_pairs ?? settings.overrides?.disabled_pairs ?? "";
    setPairs(storedPairs);
    setDisabledPairs(storedDisabled);
    setConf(String(settings.effective.min_final_confidence));
    if (settings.effective.sl_max_pct != null) setSlMaxPct(String(settings.effective.sl_max_pct));
    if (settings.effective.tp_max_pct != null) setTpMaxPct(String(settings.effective.tp_max_pct));
    setBroadcast(Boolean(settings.effective.broadcast_signals));
    setPredictionsEnabled(settings.effective.predictions_enabled !== "false");
    setOverrides(settings.overrides || {});
    setActivePairCount(settings.effective.supported_pairs?.length ?? 0);
  }

  useEffect(() => {
    setLoading(true);
    Promise.all([api("/settings"), api("/config"), api("/thresholds/active").catch(() => null)])
      .then(([settings, cfg, thresholds]) => {
        applySettingsPayload(settings);
        setThresholdSummary(thresholds);
        setConfigRows(formatServerConfig(cfg));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setError("");
    try {
      const res = await api("/settings", {
        method: "POST",
        body: JSON.stringify({
          supported_pairs: pairs,
          min_final_confidence: conf,
          sl_max_pct: slMaxPct,
          tp_max_pct: tpMaxPct,
          broadcast_signals: broadcast,
          predictions_enabled: predictionsEnabled,
          disabled_pairs: disabledPairs,
        }),
      });
      if (res.stored?.supported_pairs != null) {
        setPairs(res.stored.supported_pairs);
      } else if (Array.isArray(res.applied?.supported_pairs)) {
        setPairs(res.applied.supported_pairs.join(","));
      }
      if (res.stored?.disabled_pairs != null) {
        setDisabledPairs(res.stored.disabled_pairs);
      } else if (Array.isArray(res.applied?.disabled_pairs)) {
        setDisabledPairs(res.applied.disabled_pairs.join(","));
      }
      const refreshed = await api("/settings");
      applySettingsPayload(refreshed);
      setNotice("Settings saved");
    } catch (e) {
      setError(e.message);
    }
  }

  async function changePassword() {
    setError("");
    if (newPw.length < 8) return setError("Password must be at least 8 characters");
    if (newPw !== confirmPw) return setError("Passwords do not match");
    try {
      await api("/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: newPw }),
      });
      setNotice("Password changed");
      setCurrent("");
      setNewPw("");
      setConfirmPw("");
    } catch (e) {
      setError(e.message);
    }
  }

  if (loading) return <p className="text-[#8b949e]">Loading…</p>;

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Settings</h1>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />

      <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-medium text-white">SMC/ICT thresholds</h2>
            <p className="mt-1 text-xs text-[#8b949e]">
              Versioned detection and decision thresholds — managed in the dedicated threshold manager.
            </p>
          </div>
          <Link
            to="/thresholds"
            className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white hover:bg-[#388bfd]"
          >
            Open threshold manager
          </Link>
        </div>
        {thresholdSummary?.version ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-[#8b949e]">Active version</dt>
              <dd className="text-[#e6edf3]">{thresholdSummary.version.version_tag}</dd>
            </div>
            <div>
              <dt className="text-[#8b949e]">Version ID</dt>
              <dd className="text-[#e6edf3]">{thresholdSummary.version.id}</dd>
            </div>
            <div>
              <dt className="text-[#8b949e]">Created</dt>
              <dd className="text-[#e6edf3]">
                {thresholdSummary.version.created_at
                  ? new Date(thresholdSummary.version.created_at).toLocaleString()
                  : "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-[#8b949e]">No active threshold version — using built-in defaults.</p>
        )}
      </div>

      <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <label className="mb-1 block text-xs text-[#8b949e]">
          Supported pairs (comma separated) — saved exactly as entered. Custom pairs are merged into the platform catalog on save.
        </label>
        <p className="mb-2 text-[11px] text-[#8b949e]">
          Active in menus and predictions: {activePairCount} pair{activePairCount === 1 ? "" : "s"}.
          Use disabled pairs below to block symbols without removing them from this list.
        </p>
        <PairTextarea value={pairs} onChange={(e) => setPairs(e.target.value)} placeholder="EURUSD,GBPUSD,..." />
        <label className="mb-1 block text-xs text-[#8b949e]">Min blended confidence</label>
        <input value={conf} onChange={(e) => setConf(e.target.value)} type="number" step="0.01" min="0.3" max="0.95" className="mb-3 w-32 rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
        <div className="mb-3 flex flex-wrap gap-4">
          <div>
            <label className="mb-1 block text-xs text-[#8b949e]">Max stop-loss distance (% of price)</label>
            <input value={slMaxPct} onChange={(e) => setSlMaxPct(e.target.value)} type="number" step="0.05" min="0.05" max="2" className="w-32 rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
            <p className="mt-1 text-[11px] text-[#8b949e]">0.40% ≈ 40 pips on EURUSD</p>
          </div>
          <div>
            <label className="mb-1 block text-xs text-[#8b949e]">Max take-profit distance (% of price)</label>
            <input value={tpMaxPct} onChange={(e) => setTpMaxPct(e.target.value)} type="number" step="0.05" min="0.1" max="5" className="w-32 rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
            <p className="mt-1 text-[11px] text-[#8b949e]">Targets beyond this are never suggested</p>
          </div>
        </div>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={broadcast} onChange={(e) => setBroadcast(e.target.checked)} />
          Broadcast new signals to linked Telegram users (uses their quota)
        </label>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={predictionsEnabled} onChange={(e) => setPredictionsEnabled(e.target.checked)} />
          Predictions enabled (global kill switch)
        </label>
        <label className="mb-1 block text-xs text-[#8b949e]">Disabled pairs (comma separated)</label>
        <PairTextarea
          value={disabledPairs}
          onChange={(e) => setDisabledPairs(e.target.value)}
          placeholder="EURUSD,GBPUSD"
          rows={2}
        />
        <button type="button" onClick={save} className="mt-3 rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">Save</button>
      </div>

      {Object.keys(overrides).length > 0 && (
        <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-2 font-medium">Database overrides</h2>
          <div className="overflow-x-auto">
            <table className="w-full table-fixed text-sm">
              <colgroup>
                <col className="w-52 sm:w-64" />
                <col />
              </colgroup>
              <tbody>
                {Object.entries(overrides).map(([key, val]) => (
                  <tr key={key} className="border-t border-[#30363d] first:border-0">
                    <td className="py-3 pr-4 align-top text-[#8b949e]">{formatSettingKey(key)}</td>
                    <td className="py-3 align-top">
                      <SettingValue settingKey={key} value={val} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <h2 className="mb-3 font-medium">Change password</h2>
        <PasswordField value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Current password" autoComplete="current-password" />
        <PasswordField value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="New password" autoComplete="new-password" />
        <PasswordField value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} placeholder="Confirm" autoComplete="new-password" />
        <button type="button" onClick={changePassword} className="mt-2 rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">Change</button>
      </div>
      <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <h2 className="mb-2 font-medium">Server configuration (read-only)</h2>
        <div className="overflow-x-auto">
          <table className="w-full table-fixed text-sm">
            <colgroup>
              <col className="w-52 sm:w-64" />
              <col />
            </colgroup>
            <tbody>
              {configRows.map((row) => (
                <tr key={row.label} className="border-t border-[#30363d] first:border-0">
                  <td className="py-3 pr-4 align-top text-[#8b949e]">{row.label}</td>
                  <td className="break-words py-3 align-top">{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
