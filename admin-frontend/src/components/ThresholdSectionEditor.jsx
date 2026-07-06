import { THRESHOLD_SECTIONS } from "../constants/thresholdSections.js";
import { getSectionValue, setSectionValue } from "../utils/thresholdConfig.js";

function FieldInput({ field, value, onChange }) {
  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm text-[#c9d1d9]">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    );
  }
  return (
    <div>
      <label className="mb-1 block text-xs text-[#8b949e]">{field.label}</label>
      <input
        type={field.type === "number" ? "number" : "text"}
        value={value ?? ""}
        min={field.min}
        max={field.max}
        step={field.step}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(field.type === "number" ? (raw === "" ? "" : Number(raw)) : raw);
        }}
        className="w-full rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm text-[#e6edf3]"
      />
    </div>
  );
}

export default function ThresholdSectionEditor({ sectionId, config, baseline, onChange }) {
  const section = THRESHOLD_SECTIONS.find((s) => s.id === sectionId) || THRESHOLD_SECTIONS[0];

  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold text-white">{section.label}</h3>
      <p className="mb-4 text-xs text-[#8b949e]">{section.description || "Tune detection and decision thresholds for this section."}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {section.fields.map((field) => {
          const current = getSectionValue(config, section.id, field.key);
          const original = getSectionValue(baseline, section.id, field.key);
          const changed = current !== original;
          return (
            <div
              key={field.key}
              className={`rounded border p-3 ${changed ? "border-[#d29922]/50 bg-[#3a2d12]/20" : "border-[#30363d] bg-[#0d1117]/40"}`}
            >
              <FieldInput
                field={field}
                value={current}
                onChange={(val) => onChange(setSectionValue(config, section.id, field.key, val))}
              />
              {changed && (
                <p className="mt-1 text-[10px] text-[#d29922]">
                  was: {original == null ? "—" : String(original)}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
