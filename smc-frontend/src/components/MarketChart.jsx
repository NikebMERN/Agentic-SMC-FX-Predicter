import { useEffect, useRef, useState } from "react";

export default function MarketChart({ pair, candles = [], height = 320, lines = [] }) {
  const [live, setLive] = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!pair) return undefined;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/market/stream/${pair}`);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        setLive(JSON.parse(ev.data));
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, [pair]);

  const last = candles[candles.length - 1];
  const mid = live?.mid ?? last?.close;
  const prices = candles.flatMap((c) => [c.high, c.low, c.open, c.close]);
  lines.forEach((ln) => { if (ln?.price) prices.push(ln.price); });
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 1;
  const span = maxP - minP || 0.001;

  return (
    <div className="relative rounded border border-[#30363d] bg-[#0d1117] p-4" style={{ minHeight: height }}>
      <div className="mb-2 flex justify-between text-sm">
        <span className="font-medium">{pair}</span>
        {mid != null && (
          <span className={live ? "text-[#3fb950]" : "text-[#8b949e]"}>
            {Number(mid).toFixed(5)} {live ? "(live)" : ""}
          </span>
        )}
      </div>
      <div className="relative flex h-48 items-end gap-0.5 overflow-hidden">
        {lines.map((ln, i) => ln?.price > 0 && (
          <div
            key={i}
            className="pointer-events-none absolute left-0 right-0 border-t border-dashed opacity-70"
            style={{
              bottom: `${((ln.price - minP) / span) * 100}%`,
              borderColor: ln.color || "#888",
            }}
            title={ln.title}
          />
        ))}
        {candles.slice(-40).map((c, i) => {
          const bull = c.close >= c.open;
          const h = Math.max(4, Math.abs(c.close - c.open) / span * 100);
          return (
            <div
              key={i}
              className={`flex-1 min-w-[2px] ${bull ? "bg-[#238636]" : "bg-[#da3633]"}`}
              style={{ height: `${Math.min(100, h)}%` }}
              title={`${c.time} O:${c.open} C:${c.close}`}
            />
          );
        })}
      </div>
      <p className="mt-2 text-xs text-[#8b949e]">
        {candles.length} completed candles · live mid via WebSocket (display only)
      </p>
    </div>
  );
}
