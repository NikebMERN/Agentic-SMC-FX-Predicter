import { motion } from "framer-motion";
const MotionButton = motion.button;

export default function CurrencyCard({ symbol, onClick }) {
  const base = symbol.slice(0, 3);
  const quote = symbol.slice(3);

  return (
    <MotionButton
      type="button"
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className="rounded-xl border border-slate-700/80 bg-slate-900/80 p-4 text-left shadow-lg backdrop-blur transition hover:border-sky-500/60 hover:bg-slate-800/90"
    >
      <p className="text-xs uppercase tracking-wider text-slate-400">Forex pair</p>
      <p className="mt-1 text-xl font-bold text-white">
        {base}
        <span className="text-sky-400">/{quote}</span>
      </p>
      <p className="mt-2 text-xs text-slate-500">Tap to analyze</p>
    </MotionButton>
  );
}
