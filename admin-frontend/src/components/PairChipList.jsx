import { parsePairList } from "../utils/formatters.js";

export default function PairChipList({ value, maxHeight = "max-h-32", emptyLabel = "None" }) {
  const pairs = parsePairList(value);

  if (!pairs.length) {
    return <span className="text-[#8b949e]">{emptyLabel}</span>;
  }

  return (
    <div className={`overflow-y-auto ${maxHeight}`}>
      <div className="flex flex-wrap gap-1.5">
        {pairs.map((pair) => (
          <span
            key={pair}
            className="inline-flex rounded border border-[#30363d] bg-[#0d1117] px-2 py-0.5 font-mono text-[11px] text-[#e6edf3]"
          >
            {pair}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-[#6e7681]">{pairs.length} pair{pairs.length === 1 ? "" : "s"}</p>
    </div>
  );
}
