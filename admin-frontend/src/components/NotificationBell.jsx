import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

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

function kindLabel(kind) {
  if (kind === "feedback_conflict") return "Conflict";
  if (kind === "feedback_submitted") return "Feedback";
  if (kind === "quota_request") return "Quota";
  return kind;
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
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

  async function openItem(n) {
    if (!n.read) await markRead(n.id);
    setOpen(false);
    if (n.link) navigate(n.link.startsWith("/") ? n.link : `/${n.link}`);
  }

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        aria-label="Notifications"
        onClick={() => setOpen((v) => !v)}
        className="relative rounded border border-[#30363d] p-2 text-[#e6edf3] hover:border-[#8b949e]"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#f85149] px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-lg border border-[#30363d] bg-[#161b22] shadow-xl">
          <div className="flex items-center justify-between border-b border-[#30363d] px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                disabled={loading}
                onClick={markAllRead}
                className="text-xs text-[#2f81f7] hover:underline disabled:opacity-50"
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-80 overflow-y-auto">
            {items.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-[#8b949e]">No notifications yet</li>
            )}
            {items.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => openItem(n)}
                  className={`w-full border-b border-[#21262d] px-3 py-2 text-left hover:bg-[#21262d] ${
                    n.read ? "opacity-70" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium">{n.title}</span>
                    <span className="shrink-0 rounded bg-[#21262d] px-1.5 py-0.5 text-[10px] uppercase text-[#8b949e]">
                      {kindLabel(n.kind)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[#8b949e] line-clamp-2">{n.body}</p>
                  {n.meta?.user_feedback && n.meta?.market_direction && (
                    <p className="mt-1 text-[11px] text-[#f0883e]">
                      User: {n.meta.user_feedback} · Market: {n.meta.market_direction}
                    </p>
                  )}
                  <p className="mt-1 text-[10px] text-[#6e7681]">{timeAgo(n.created_at)}</p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
