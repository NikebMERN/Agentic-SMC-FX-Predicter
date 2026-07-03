import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function PublicLayout() {
  const { isAuthenticated, profile, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-sky-400">
            SmartFlow AI
          </Link>
            <nav className="flex items-center gap-3 text-sm">
            <Link to="/" className="hover:text-sky-300">Home</Link>
            {isAuthenticated ? (
              <>
                <Link to="/feedback" className="hover:text-sky-300">My feedback</Link>
                <Link to="/history" className="hover:text-sky-300">History</Link>
                <Link to="/predict" className="hover:text-sky-300">Predict</Link>
                <Link to="/telegram" className="hover:text-sky-300">Telegram</Link>
                {profile && (
                  <span className="hidden text-slate-400 sm:inline">
                    {profile.username} · quota {profile.signals_remaining ?? 0}
                  </span>
                )}
                <button type="button" onClick={handleLogout} className="text-slate-400 hover:text-white">
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="rounded-md border border-slate-600 px-3 py-1 hover:border-sky-500">
                  Sign in
                </Link>
                <Link to="/register" className="rounded-md bg-sky-600 px-3 py-1 text-white hover:bg-sky-500">
                  Register
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
