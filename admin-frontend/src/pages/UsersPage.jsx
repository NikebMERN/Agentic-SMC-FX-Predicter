import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import { withNotice } from "../hooks/usePageLoad.js";

export default function UsersPage() {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState([]);
  const [quotaDraft, setQuotaDraft] = useState({});
  const [approveQuota, setApproveQuota] = useState({});
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadUsers = useCallback(async (search = q) => {
    setLoading(true);
    setActionError("");
    try {
      const d = await api(`/users${search ? `?q=${encodeURIComponent(search)}` : ""}`);
      setUsers(d.users || []);
      const drafts = {};
      (d.users || []).forEach((u) => {
        drafts[u.id] = u.signals_remaining ?? 0;
      });
      setQuotaDraft(drafts);
    } catch (e) {
      setActionError(e.message);
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => {
    loadUsers("");
  }, []);

  async function act(fn, successMsg) {
    try {
      await withNotice(setNotice, setActionError, fn, successMsg);
      await reload();
    } catch {
      /* error shown in banner */
    }
  }

  async function reload() {
    await loadUsers(q);
  }

  async function setRole(id, role) {
    await act(() => api(`/users/${id}/role`, { method: "POST", body: JSON.stringify({ role }) }), `Role updated to ${role}`);
  }

  async function setBan(id, banned) {
    await act(() => api(`/users/${id}/ban`, { method: "POST", body: JSON.stringify({ banned }) }), banned ? "User banned" : "User unbanned");
  }

  async function approveUser(id) {
    const n = parseInt(approveQuota[id] ?? quotaDraft[id] ?? "5", 10);
    if (Number.isNaN(n) || n < 0) return setActionError("Quota must be a non-negative number");
    await act(
      () => api(`/users/${id}/approve`, { method: "POST", body: JSON.stringify({ signals_remaining: n }) }),
      "User approved"
    );
  }

  async function delUser(id) {
    if (!confirm(`Delete user ${id}?`)) return;
    await act(() => api(`/users/${id}`, { method: "DELETE" }), "User deleted");
  }

  async function setQuota(id) {
    const n = parseInt(quotaDraft[id], 10);
    if (Number.isNaN(n) || n < 0) return setActionError("Quota must be a non-negative number");
    await act(() => api(`/users/${id}/quota`, { method: "POST", body: JSON.stringify({ signals_remaining: n }) }), "Quota updated");
  }

  function statusLabel(u) {
    const s = u.status || (u.is_active ? "active" : "pending");
    if (s === "pending") return "pending approval";
    if (s === "banned") return "banned";
    return "active";
  }

  const isBanned = (u) => u.status === "banned";
  const isPending = (u) => u.status === "pending" || (!u.is_active && u.status !== "banned");

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Users</h1>
      <p className="mb-4 text-sm text-[#8b949e]">
        New registrations start as <strong>pending</strong> with 0 predictions until you approve them. Click a username for full history.
      </p>
      <div className="mb-4 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search username / email" className="rounded border border-[#30363d] bg-[#0d1117] px-3 py-1.5 text-sm" />
        <button onClick={reload} disabled={loading} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white disabled:opacity-50">
          {loading ? "Loading…" : "Search"}
        </button>
      </div>
      <PageAlerts error={actionError} notice={notice} onClearNotice={() => setNotice("")} />
      <div className="overflow-x-auto rounded-lg border border-[#30363d]">
        <table className="w-full text-sm">
          <thead className="bg-[#161b22] text-left text-[#8b949e]">
            <tr>
              <th className="p-2">ID</th><th>Username</th><th>Email</th><th>Role</th><th>Quota</th><th>Status</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && !loading && (
              <tr><td colSpan={7} className="p-4 text-center text-[#8b949e]">No users found</td></tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="border-t border-[#30363d]">
                <td className="p-2">{u.id}</td>
                <td>
                  <Link to={`/users/${u.id}`} className="text-[#2f81f7] hover:underline">{u.username}</Link>
                </td>
                <td>{u.email}</td>
                <td>{u.role}</td>
                <td className="whitespace-nowrap">
                  <input
                    type="number"
                    min="0"
                    value={quotaDraft[u.id] ?? u.signals_remaining ?? 0}
                    onChange={(e) => setQuotaDraft({ ...quotaDraft, [u.id]: e.target.value })}
                    className="mr-1 w-16 rounded border border-[#30363d] bg-[#0d1117] px-1 py-0.5 text-xs"
                  />
                  <button type="button" onClick={() => setQuota(u.id)} className="text-[#2f81f7]">Set</button>
                </td>
                <td>{statusLabel(u)}</td>
                <td className="space-x-1 whitespace-nowrap">
                  {isPending(u) && (
                    <>
                      <input
                        type="number"
                        min="0"
                        placeholder="5"
                        value={approveQuota[u.id] ?? quotaDraft[u.id] ?? 5}
                        onChange={(e) => setApproveQuota({ ...approveQuota, [u.id]: e.target.value })}
                        className="mr-1 w-14 rounded border border-[#30363d] bg-[#0d1117] px-1 py-0.5 text-xs"
                      />
                      <button type="button" onClick={() => approveUser(u.id)} className="rounded bg-[#238636] px-2 py-0.5 text-xs text-white">Approve</button>
                    </>
                  )}
                  <button type="button" onClick={() => setRole(u.id, u.role === "admin" ? "user" : "admin")} className="rounded border border-[#30363d] px-2 py-0.5 text-xs">{u.role === "admin" ? "Demote" : "Promote"}</button>
                  {!isPending(u) && (
                    <button type="button" onClick={() => setBan(u.id, !isBanned(u))} className="rounded border border-[#30363d] px-2 py-0.5 text-xs">{isBanned(u) ? "Unban" : "Ban"}</button>
                  )}
                  <button type="button" onClick={() => delUser(u.id)} className="rounded border border-[#f85149] px-2 py-0.5 text-xs text-[#f85149]">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
