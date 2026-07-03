import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function Layout() {
  const { logout, profile } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <Link to="/dashboard" className="font-semibold text-sky-400">
            SmartFlow AI
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link to="/dashboard" className="hover:text-sky-300">Dashboard</Link>
            <Link to="/predict" className="hover:text-sky-300">Predict</Link>
            <Link to="/telegram" className="hover:text-sky-300">Telegram</Link>
            {profile && (
              <span className="text-slate-400">Quota: {profile.signals_remaining ?? "—"}</span>
            )}
            <button type="button" onClick={handleLogout} className="text-slate-400 hover:text-white">
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
