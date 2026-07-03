import { useState } from "react";
import { api } from "../api/client.js";

export default function TelegramPage() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function generateCode() {
    setLoading(true);
    setError("");
    try {
      const res = await api("/telegram/link-code", { method: "POST" });
      setCode(res.code);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold">Telegram</h1>

      <div className="mb-6 rounded-lg border border-slate-700 bg-slate-900 p-4 text-sm text-slate-300">
        <p className="mb-2">
          <strong>New:</strong> sending <code className="text-sky-300">/start</code> to the bot automatically
          registers your Telegram as a platform account (pending admin approval).
        </p>
        <p>
          If you registered on the web first, generate a link code below and send{" "}
          <code className="text-sky-300">/link CODE</code> in Telegram to merge accounts.
        </p>
      </div>

      <button
        onClick={generateCode}
        disabled={loading}
        className="rounded bg-sky-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {loading ? "Generating…" : "Generate web link code"}
      </button>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      {code && (
        <div className="mt-4 rounded-lg border border-slate-700 bg-slate-900 p-4">
          <p className="text-sm text-slate-400">One-time code (15 min):</p>
          <p className="mt-2 text-2xl font-mono tracking-widest text-sky-300">{code}</p>
          <p className="mt-3 text-sm text-slate-400">
            In Telegram: <strong>/link {code}</strong>
          </p>
        </div>
      )}
    </div>
  );
}
