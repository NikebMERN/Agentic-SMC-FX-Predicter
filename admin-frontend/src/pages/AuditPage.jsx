import { Fragment, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { formatAuditDetail } from "../utils/formatters.js";

function formatDetail(raw) {
  const readable = formatAuditDetail(raw);
  if (readable) return readable;
  if (!raw) return "";
  if (typeof raw === "string") {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }
  return JSON.stringify(raw, null, 2);
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [logs, setLogs] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadLogs(search = action) {
    setLoading(true);
    setError("");
    try {
      const d = await api(`/audit${search ? `?action=${encodeURIComponent(search)}` : ""}`);
      setLogs(d.logs || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLogs("");
  }, []);

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Admin audit log</h1>
      <div className="mb-4 flex gap-2">
        <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter by action (e.g. ban, approve_user)" className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-1.5 text-sm" />
        <button type="button" onClick={() => loadLogs(action)} disabled={loading} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white disabled:opacity-50">{loading ? "Loading…" : "Search"}</button>
      </div>
      <PageAlerts error={error} />
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="text-left text-[#8b949e]">
            <tr><th className="p-2">ID</th><th>Admin</th><th>Action</th><th>Target</th><th>IP</th><th>When</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {logs.length === 0 && !loading && (
              <tr><td colSpan={7} className="p-4 text-center text-[#8b949e]">No audit entries</td></tr>
            )}
            {logs.map((l) => (
              <Fragment key={l.id}>
                <tr className="border-t border-[#30363d]">
                  <td className="p-2">{l.id}</td>
                  <td>{l.admin_id ?? "-"}</td>
                  <td>{l.action}</td>
                  <td>{l.target_type} {l.target_id ?? ""}</td>
                  <td>{l.ip ?? "-"}</td>
                  <td className="text-xs text-[#8b949e]">{l.created_at ? String(l.created_at).slice(0, 19) : "-"}</td>
                  <td>
                    {l.detail_json ? (
                      <button type="button" onClick={() => setExpanded(expanded === l.id ? null : l.id)} className="text-xs text-[#2f81f7]">
                        {expanded === l.id ? "Hide" : "View"}
                      </button>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
                {expanded === l.id && l.detail_json && (
                  <tr className="border-t border-[#30363d] bg-[#0d1117]">
                    <td colSpan={7} className="p-3">
                      <pre className="overflow-auto text-xs text-[#8b949e]">{formatDetail(l.detail_json)}</pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
