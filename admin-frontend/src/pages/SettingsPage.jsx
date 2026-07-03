import { useEffect, useState } from "react";
import PasswordField from "../components/PasswordField.jsx";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { formatServerConfig, formatSettingKey, formatSettingValue } from "../utils/formatters.js";

export default function SettingsPage() {
  const [pairs, setPairs] = useState("");
  const [conf, setConf] = useState("0.55");
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([api("/settings"), api("/config")])
      .then(([settings, cfg]) => {
        setPairs(settings.effective.supported_pairs.join(","));
        setConf(String(settings.effective.min_final_confidence));
        setBroadcast(Boolean(settings.effective.broadcast_signals));
        setPredictionsEnabled(settings.effective.predictions_enabled !== "false");
        setDisabledPairs(settings.effective.disabled_pairs || "");
        setOverrides(settings.overrides || {});
        setConfigRows(formatServerConfig(cfg));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setError("");
    try {
      await api("/settings", {
        method: "POST",
        body: JSON.stringify({
          supported_pairs: pairs,
          min_final_confidence: conf,
          broadcast_signals: broadcast,
          predictions_enabled: predictionsEnabled,
          disabled_pairs: disabledPairs,
        }),
      });
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
        <label className="mb-1 block text-xs text-[#8b949e]">Pair list (comma separated — full 96-pair catalog is always active; use disabled pairs below to block symbols)</label>
        <input value={pairs} onChange={(e) => setPairs(e.target.value)} className="mb-3 w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
        <label className="mb-1 block text-xs text-[#8b949e]">Min blended confidence</label>
        <input value={conf} onChange={(e) => setConf(e.target.value)} type="number" step="0.01" min="0.3" max="0.95" className="mb-3 w-32 rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={broadcast} onChange={(e) => setBroadcast(e.target.checked)} />
          Broadcast new signals to linked Telegram users (uses their quota)
        </label>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={predictionsEnabled} onChange={(e) => setPredictionsEnabled(e.target.checked)} />
          Predictions enabled (global kill switch)
        </label>
        <label className="mb-1 block text-xs text-[#8b949e]">Disabled pairs (comma separated)</label>
        <input
          value={disabledPairs}
          onChange={(e) => setDisabledPairs(e.target.value)}
          placeholder="EURUSD,GBPUSD"
          className="mb-3 w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm"
        />
        <button type="button" onClick={save} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">Save</button>
      </div>
      {Object.keys(overrides).length > 0 && (
        <div className="mb-6 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-2 font-medium">Database overrides</h2>
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(overrides).map(([key, val]) => (
                <tr key={key} className="border-t border-[#30363d] first:border-0">
                  <td className="py-2 pr-4 text-[#8b949e]">{formatSettingKey(key)}</td>
                  <td>{formatSettingValue(key, val)}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
        <table className="w-full text-sm">
          <tbody>
            {configRows.map((row) => (
              <tr key={row.label} className="border-t border-[#30363d] first:border-0">
                <td className="py-2 pr-4 text-[#8b949e]">{row.label}</td>
                <td>{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
