import { useState } from "react";
import { Link } from "react-router-dom";
import PasswordField from "../components/PasswordField.jsx";
import { api } from "../api/client.js";

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await api("/register", {
        method: "POST",
        body: JSON.stringify({ username, email, password }),
      });
      setPending(true);
    } catch (err) {
      setError(err.message);
    }
  }

  if (pending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
        <div className="max-w-md rounded-lg border border-slate-700 bg-slate-900 p-8 text-center">
          <h1 className="mb-2 text-xl font-semibold">Registration received</h1>
          <p className="mb-4 text-sm text-slate-400">
            An admin must approve your account before predictions are enabled.
            You can sign in now to check your status and feedback history.
          </p>
          <Link to="/login" className="text-sky-400 text-sm">Sign in</Link>
          {" · "}
          <Link to="/" className="text-sky-400 text-sm">Browse pairs</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-8">
        <h1 className="mb-6 text-xl font-semibold">Create account</h1>
        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" className="mb-3 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm" />
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="mb-3 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm" />
        <PasswordField value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password (min 8 chars)" autoComplete="new-password" />
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
        <button type="submit" className="w-full rounded-md bg-sky-600 py-2 text-sm font-medium text-white">
          Register
        </button>
        <p className="mt-4 text-center text-sm text-slate-400">
          Already have an account? <Link to="/login" className="text-sky-400">Sign in</Link>
        </p>
        <p className="mt-2 text-center text-sm">
          <Link to="/" className="text-slate-500 hover:text-sky-400">← Back to currency list</Link>
        </p>
      </form>
    </div>
  );
}
