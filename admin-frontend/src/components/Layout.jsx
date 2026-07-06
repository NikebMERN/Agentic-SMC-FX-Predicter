import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import NotificationBell from "./NotificationBell.jsx";

const NAV = [
  ["dashboard", "Dashboard"],
  ["users", "Users"],
  ["signals", "Signals"],
  ["trades", "Trades"],
  ["models", "Models & Data"],
  ["reviews", "AI Reviews"],
  ["training-records", "Training Records"],
  ["predict", "Predict"],
  ["settings", "Settings"],
  ["thresholds", "Thresholds"],
  ["ml-ops", "ML Operations"],
  ["logs", "Logs"],
  ["audit", "Audit"],
];

export default function Layout() {
  const { logout, username } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-52 flex-col border-r border-[#30363d] bg-[#161b22]">
        <div className="px-4 py-5 text-sm font-bold">SmartFlow AI</div>
        <nav className="flex-1 space-y-0.5">
          {NAV.map(([path, label]) => (
            <NavLink
              key={path}
              to={`/${path}`}
              className={({ isActive }) =>
                `block px-4 py-2 text-sm ${
                  isActive
                    ? "border-l-2 border-[#2f81f7] bg-[#21262d] text-white"
                    : "text-[#8b949e] hover:text-white"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-[#30363d] p-4 text-xs text-[#8b949e]">
          {username && <div className="mb-2">{username}</div>}
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="rounded border border-[#30363d] px-3 py-1 text-sm text-[#e6edf3] hover:border-[#8b949e]"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex flex-1 flex-col overflow-y-auto">
        <header className="sticky top-0 z-10 flex items-center justify-end gap-3 border-b border-[#30363d] bg-[#0d1117]/95 px-6 py-3 backdrop-blur">
          <NotificationBell />
        </header>
        <div className="flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
