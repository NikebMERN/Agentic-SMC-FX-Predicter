import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const LEVELS = ["ALL", "ERROR", "WARNING", "INFO"];

function formatLogLine(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) return line;
  try {
    const obj = JSON.parse(trimmed);
    const parts = [];
    if (obj.timestamp || obj.time) parts.push(obj.timestamp || obj.time);
    if (obj.level) parts.push(`[${obj.level}]`);
    if (obj.logger || obj.name) parts.push(obj.logger || obj.name);
    if (obj.message) parts.push(obj.message);
    else if (obj.msg) parts.push(obj.msg);
    if (parts.length) return parts.join(" ");
    return JSON.stringify(obj, null, 2);
  } catch {
    return line;
  }
}

export default function LogsPage() {
  const [lines, setLines] = useState([]);
  const [auto, setAuto] = useState(false);
  const [level, setLevel] = useState("ALL");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api("/logs?lines=300");
      setLines(d.lines || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [auto, load]);

  const filtered = useMemo(() => {
    if (level === "ALL") return lines;
    return lines.filter((ln) => ln.toUpperCase().includes(level));
  }, [lines, level]);

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Logs</h1>
      <PageAlerts error={error} />
      <div className="mb-3 flex flex-wrap gap-3">
        <button type="button" onClick={load} className="rounded border border-[#30363d] px-3 py-1 text-sm">Refresh</button>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> auto-refresh (5s)
        </label>
        <select value={level} onChange={(e) => setLevel(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          {LEVELS.map((l) => (
            <option key={l} value={l}>{l === "ALL" ? "All levels" : l}</option>
          ))}
        </select>
        <span className="text-xs text-[#8b949e]">{filtered.length} lines</span>
      </div>
      <pre className="max-h-[70vh] overflow-auto rounded border border-[#30363d] bg-[#0d1117] p-3 text-xs whitespace-pre-wrap">
        {filtered.map(formatLogLine).join("\n") || "No log lines"}
      </pre>
    </div>
  );
}
