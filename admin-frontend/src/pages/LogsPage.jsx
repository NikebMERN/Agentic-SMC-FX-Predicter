import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

const LEVELS = ["ALL", "CRITICAL", "ERROR", "WARNING", "INFO"];
const SOURCES = ["ALL", "application", "api", "trading_engine", "prediction", "telegram", "worker", "scheduler", "ml_training", "database", "deployment"];

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
  const [source, setSource] = useState("ALL");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ lines: "500" });
      if (level !== "ALL") params.set("severity", level);
      if (source !== "ALL") params.set("source", source);
      if (search) params.set("search", search);
      if (dateFrom) params.set("from", dateFrom);
      if (dateTo) params.set("to", dateTo);
      const d = await api(`/logs?${params}`);
      setLines(d.lines || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [level, source, search, dateFrom, dateTo]);

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
        <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm">
          {SOURCES.map((item) => <option key={item} value={item}>{item === "ALL" ? "All systems" : item.replaceAll("_", " ")}</option>)}
        </select>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search logs" className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
        <span className="text-xs text-[#8b949e]">{filtered.length} lines</span>
      </div>
      <pre className="max-h-[70vh] overflow-auto rounded border border-[#30363d] bg-[#0d1117] p-3 text-xs whitespace-pre-wrap">
        {filtered.map(formatLogLine).join("\n") || "No log lines"}
      </pre>
    </div>
  );
}
