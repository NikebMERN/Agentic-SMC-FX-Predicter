import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";

export default function OperationsPage() {
  const [jobs, setJobs] = useState({ training: [], exports: [], deliveries: [] });
  const [service, setService] = useState("ai-worker");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(() => api("/jobs").then(setJobs).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function restart() {
    if (!window.confirm(`Request production restart for ${service}?`)) return;
    try {
      await api("/system/restart", {
        method: "POST",
        body: JSON.stringify({ service, confirmation: `RESTART ${service}` }),
      });
      setNotice(`Restart requested for ${service}`);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Operations</h1>
        <p className="text-sm text-[#8b949e]">Production jobs, queues, failure recovery, and guarded service controls.</p>
      </div>
      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />
      <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
        <h2 className="mb-2 font-medium">Service restart</h2>
        <div className="flex gap-2">
          <select value={service} onChange={(e) => setService(e.target.value)} className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm">
            {["api", "ai-worker", "scheduler", "all"].map((item) => <option key={item}>{item}</option>)}
          </select>
          <button type="button" onClick={restart} className="rounded bg-[#da3633] px-3 py-2 text-sm text-white">Request restart</button>
        </div>
        <p className="mt-2 text-xs text-[#8b949e]">Requires the deployment-controlled `SYSTEM_RESTART_WEBHOOK`; no shell commands are exposed.</p>
      </section>
      {[
        ["Training jobs", jobs.training],
        ["Export jobs", jobs.exports],
        ["Notification delivery exceptions", jobs.deliveries],
      ].map(([title, rows]) => (
        <section key={title} className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-2 font-medium">{title}</h2>
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[#8b949e]"><tr><th className="pb-2">ID</th><th>Status</th><th>Created</th><th>Error</th></tr></thead>
              <tbody>
                {(rows || []).map((row) => (
                  <tr key={row.id} className="border-t border-[#30363d]">
                    <td className="py-2">{row.id}</td><td>{row.status}</td>
                    <td>{row.created_at?.slice?.(0, 19) ?? "—"}</td>
                    <td className="max-w-md truncate text-[#f85149]">{row.error_message || row.last_error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
