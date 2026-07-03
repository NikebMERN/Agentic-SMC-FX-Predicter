import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import PasswordField from "../components/PasswordField.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { api, forgotPassword, resetPassword } from "../api/client.js";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [step, setStep] = useState("login");
  const [code, setCode] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-96 rounded-lg border border-[#30363d] bg-[#161b22] p-8">
        <h1 className="mb-6 text-lg font-semibold">SmartFlow AI — Admin</h1>

        {step === "login" && (
          <form onSubmit={handleLogin}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="mb-3 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm"
            />
            <PasswordField value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" />
            {error && <p className="mb-3 text-sm text-[#f85149]">{error}</p>}
            <button type="submit" className="w-full rounded-md bg-[#2f81f7] py-2 text-sm font-medium text-white">
              Sign in
            </button>
            <button type="button" onClick={() => setStep("forgot1")} className="mt-3 w-full text-sm text-[#2f81f7]">
              Forgot password?
            </button>
          </form>
        )}

        {step === "forgot1" && (
          <div>
            <p className="mb-3 text-sm text-[#8b949e]">Enter your account email — we&apos;ll send a 6-digit reset code.</p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="mb-3 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={async () => {
                setError("");
                try {
                  await forgotPassword(email);
                  setStep("forgot2");
                } catch (err) {
                  setError(err.message);
                }
              }}
              className="w-full rounded-md bg-[#2f81f7] py-2 text-sm text-white"
            >
              Send reset code
            </button>
            <button type="button" onClick={() => setStep("login")} className="mt-3 w-full text-sm text-[#2f81f7]">
              Back to sign in
            </button>
          </div>
        )}

        {step === "forgot2" && (
          <div>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="6-digit code" maxLength={6} className="mb-3 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm" />
            <PasswordField value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="New password" autoComplete="new-password" />
            <PasswordField value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} placeholder="Confirm password" autoComplete="new-password" />
            <button
              type="button"
              onClick={async () => {
                setError("");
                if (newPw.length < 8) return setError("Password must be at least 8 characters");
                if (newPw !== confirmPw) return setError("Passwords do not match");
                try {
                  await resetPassword(email, code, newPw);
                  setStep("login");
                  setError("");
                } catch (err) {
                  setError(err.message);
                }
              }}
              className="w-full rounded-md bg-[#2f81f7] py-2 text-sm text-white"
            >
              Reset password
            </button>
          </div>
        )}

        {error && step !== "login" && <p className="mt-3 text-sm text-[#f85149]">{error}</p>}
      </div>
    </div>
  );
}
