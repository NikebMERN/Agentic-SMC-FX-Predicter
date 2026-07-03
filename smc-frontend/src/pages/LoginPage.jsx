import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import PasswordField from "../components/PasswordField.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { forgotPassword, resetPassword } from "../api/client.js";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from || "/feedback";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [step, setStep] = useState("login");
  const [code, setCode] = useState("");
  const [newPw, setNewPw] = useState("");
  const [devCode, setDevCode] = useState("");

  if (isAuthenticated) return <Navigate to={redirectTo} replace />;

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const res = await login(email, password);
      navigate(res.status === "pending" && !String(redirectTo).startsWith("/predict") ? "/feedback" : redirectTo);
    } catch (err) {
      if (err.status === 403 && err.body?.status === "banned") {
        setError("Account suspended.");
      } else {
        setError(err.message);
      }
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-8">
        <h1 className="mb-2 text-xl font-semibold text-white">Sign in</h1>
        <p className="mb-6 text-sm text-slate-400">SmartFlow AI — SMC/ICT predictions</p>

        {step === "login" && (
          <form onSubmit={handleLogin}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="mb-3 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
            />
            <PasswordField value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" />
            {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
            <button type="submit" className="w-full rounded-md bg-sky-600 py-2 text-sm font-medium text-white hover:bg-sky-500">
              Sign in
            </button>
            <button type="button" onClick={() => setStep("forgot1")} className="mt-3 w-full text-sm text-sky-400">
              Forgot password?
            </button>
          <p className="mt-4 text-center text-sm text-slate-400">
            No account? <Link to="/register" className="text-sky-400">Register for approval</Link>
          </p>
          <p className="mt-2 text-center text-sm">
            <Link to="/" className="text-slate-500 hover:text-sky-400">← Back to currency list</Link>
          </p>
          </form>
        )}

        {step === "forgot1" && (
          <div>
            <p className="mb-3 text-sm text-slate-400">Enter your email for a 6-digit reset code.</p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="mb-3 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={async () => {
                setError("");
                try {
                  const res = await forgotPassword(email);
                  if (res.dev_code) setDevCode(res.dev_code);
                  setStep("forgot2");
                } catch (err) {
                  setError(err.message);
                }
              }}
              className="w-full rounded-md bg-sky-600 py-2 text-sm text-white"
            >
              Send reset code
            </button>
            <button type="button" onClick={() => setStep("login")} className="mt-3 w-full text-sm text-sky-400">
              Back
            </button>
          </div>
        )}

        {step === "forgot2" && (
          <div>
            {devCode && (
              <p className="mb-3 rounded bg-amber-950/50 p-2 text-sm text-amber-200">
                Dev code (SMTP off): <strong>{devCode}</strong>
              </p>
            )}
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="6-digit code" maxLength={6} className="mb-3 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm" />
            <PasswordField value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="New password" autoComplete="new-password" />
            <button
              type="button"
              onClick={async () => {
                setError("");
                try {
                  await resetPassword(email, code, newPw);
                  setStep("login");
                } catch (err) {
                  setError(err.message);
                }
              }}
              className="w-full rounded-md bg-sky-600 py-2 text-sm text-white"
            >
              Reset password
            </button>
          </div>
        )}

        {error && step !== "login" && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </div>
    </div>
  );
}
