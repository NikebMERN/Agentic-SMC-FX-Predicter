import { useState } from "react";

export default function PasswordField({ value, onChange, placeholder, autoComplete }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative mb-3">
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 pr-10 text-sm"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-[#8b949e] hover:text-white"
        aria-label={show ? "Hide password" : "Show password"}
      >
        {show ? "🙈" : "👁"}
      </button>
    </div>
  );
}
