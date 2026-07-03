import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const [quotaMsg, setQuotaMsg] = useState("");
  const wrapRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await api("/notifications?limit=20");
      setItems(data.notifications || []);
      setUnread(data.unread_count ?? 0);
    } catch {
      /* ignore poll errors */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 45000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  async function markRead(id) {
    try {
      await api(`/notifications/${id}/read`, { method: "PATCH" });
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      setUnread((c) => Math.max(0, c - 1));
    } catch {
      /* ignore */
    }
  }

  async function markAllRead() {
    setLoading(true);
    try {
      const data = await api("/notifications/read-all", { method: "POST" });
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnread(data.unread_count ?? 0);
    } finally {
      setLoading(false);
    }
  }

  async function requestQuota() {
    setQuotaMsg("");
    setLoading(true);
    try {
      const data = await api("/my/quota-request", {
        method: "POST",
        body: JSON.stringify({
          message: profile?.signals_remaining === 0
            ? "Free trial quota exhausted — please add more predictions."
            : "Requesting additional prediction quota.",
        }),
      });
      setQuotaMsg(data.message || "Request sent.");
    } catch (err) {
      setQuotaMsg(err.message || "Could not send request.");
    } finally {
      setLoading(false);
    }
  }

  async function openItem(n) {
    if (!n.read) await markRead(n.id);
    setOpen(false);
    if (n.link) navigate(n.link.startsWith("/") ? n.link : `/${n.link}`);
  }

  const showQuotaCta = profile && (profile.signals_remaining ?? 0) <= 2;

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        aria-label="Notifications"
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-md border border-slate-700 p-2 text-slate-200 hover:border-sky-500"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-700 bg-slate-900 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                disabled={loading}
                onClick={markAllRead}
                className="text-xs text-sky-400 hover:underline disabled:opacity-50"
              >
                Mark all read
              </button>
            )}
          </div>

          {showQuotaCta && (
            <div className="border-b border-slate-800 px-3 py-2">
              <button
                type="button"
                disabled={loading}
                onClick={requestQuota}
                className="w-full rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                Request more quota ({profile.signals_remaining ?? 0} left)
              </button>
              {quotaMsg && <p className="mt-1 text-[11px] text-slate-400">{quotaMsg}</p>}
            </div>
          )}

          <ul className="max-h-80 overflow-y-auto">
            {items.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-500">No notifications yet</li>
            )}
            {items.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => openItem(n)}
                  className={`w-full border-b border-slate-800 px-3 py-2 text-left hover:bg-slate-800/80 ${
                    n.read ? "opacity-70" : ""
                  }`}
                >
                  <p className="text-sm font-medium">{n.title}</p>
                  <p className="mt-1 text-xs text-slate-400 line-clamp-2">{n.body}</p>
                  <p className="mt-1 text-[10px] text-slate-500">{timeAgo(n.created_at)}</p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
