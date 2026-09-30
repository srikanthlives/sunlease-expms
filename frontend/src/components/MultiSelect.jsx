import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

// Checkbox dropdown. options: [{value, label}], value: array of selected values.
export default function MultiSelect({ label, options, value, onChange, placeholder = "All", disabled = false, className = "" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function close(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const selected = options.filter((o) => value.includes(String(o.value)));
  const summary = selected.length === 0 ? placeholder : selected.length === 1 ? selected[0].label : `${selected.length} selected`;

  function toggle(v) {
    const s = String(v);
    onChange(value.includes(s) ? value.filter((x) => x !== s) : [...value, s]);
  }

  return (
    <div className={`relative ${className}`} ref={ref}>
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <button
        type="button" disabled={disabled} onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 rounded-md border border-ink/15 px-3 py-2 text-sm bg-white text-left disabled:opacity-50 focus:border-brand-500 outline-none"
      >
        <span className={`truncate ${selected.length === 0 ? "text-ink/50" : ""}`}>{summary}</span>
        <ChevronDown size={14} className="shrink-0 text-ink/40" />
      </button>
      {open && !disabled && (
        <div className="absolute z-20 mt-1 w-full min-w-[12rem] max-h-64 overflow-auto rounded-md border border-ink/15 bg-white shadow-lg py-1">
          {value.length > 0 && (
            <button type="button" onClick={() => onChange([])} className="w-full text-left px-3 py-1.5 text-xs text-brand-700 hover:bg-brand-50">Clear selection</button>
          )}
          {options.length === 0 && <div className="px-3 py-2 text-xs text-ink/40">No options</div>}
          {options.map((o) => (
            <label key={o.value} className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-brand-50">
              <input type="checkbox" checked={value.includes(String(o.value))} onChange={() => toggle(o.value)} />
              <span className="truncate">{o.label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
