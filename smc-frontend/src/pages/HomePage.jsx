import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import CurrencyCard from "../components/CurrencyCard.jsx";
import { useAuth } from "../context/AuthContext.jsx";

async function fetchPairs() {
  const res = await fetch("/pairs");
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Failed to load pairs");
  return body;
}

export default function HomePage() {
  const [pairs, setPairs] = useState([]);
  const [interval, setInterval] = useState("60min");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    fetchPairs()
      .then((data) => {
        setPairs(data.pairs || []);
        if (data.interval) setInterval(data.interval);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = pairs.filter((p) => p.toLowerCase().includes(search.toLowerCase()));

  const grouped = filtered.reduce((acc, pair) => {
    const letter = pair[0]?.toUpperCase() || "#";
    if (!acc[letter]) acc[letter] = [];
    acc[letter].push(pair);
    return acc;
  }, {});

  function handlePairClick(symbol) {
    if (!isAuthenticated) {
      navigate("/login", { state: { from: `/predict/${symbol}` } });
      return;
    }
    navigate(`/predict/${symbol}`);
  }

  return (
    <div className="relative min-h-[calc(100vh-57px)] bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 px-4 py-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),_transparent_55%)]" />
      <div className="relative mx-auto max-w-6xl">
        <div className="mb-8 text-center">
          <h1 className="mb-2 text-3xl font-bold text-white md:text-4xl">Currency predictions</h1>
          <p className="text-slate-400">
            SMC + ICT confluence engine · interval {interval} · {pairs.length} pairs
            {!isAuthenticated && " · register or sign in to analyze"}
          </p>
        </div>

        <input
          type="search"
          placeholder="Search currency pairs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mx-auto mb-8 block w-full max-w-md rounded-full border border-slate-700 bg-slate-900/80 px-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />

        {loading && <p className="text-center text-slate-400">Loading pairs…</p>}
        {error && <p className="text-center text-red-400">{error}</p>}

        {!loading && !error && (
          <div className="space-y-8">
            {Object.keys(grouped)
              .sort()
              .map((letter) => (
                <section key={letter}>
                  <h2 className="mb-3 border-b border-slate-800 pb-1 text-2xl font-semibold text-sky-300/90">
                    {letter}
                  </h2>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                    {grouped[letter].map((pair) => (
                      <CurrencyCard key={pair} symbol={pair} onClick={() => handlePairClick(pair)} />
                    ))}
                  </div>
                </section>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
