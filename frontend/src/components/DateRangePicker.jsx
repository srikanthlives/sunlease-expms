import { Input } from "./ui";

function isoDaysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}
function isoMonthsAgo(months) {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}
function isoToday() {
  return new Date().toISOString().slice(0, 10);
}
function startOfYear(yearsAgo = 0) {
  const d = new Date();
  return `${d.getFullYear() - yearsAgo}-01-01`;
}

export function buildPresets(bounds) {
  const today = isoToday();
  const earliest = bounds?.earliest || isoMonthsAgo(12);
  return [
    { label: "This Month", from: today.slice(0, 8) + "01", to: today },
    { label: "Last 3 Months", from: isoMonthsAgo(3), to: today },
    { label: "Last 6 Months", from: isoMonthsAgo(6), to: today },
    { label: "This Year", from: startOfYear(), to: today },
    { label: "Last 12 Months", from: isoMonthsAgo(12), to: today },
    { label: "All Time", from: earliest, to: today },
  ];
}

/**
 * A from/to date pair with quick preset buttons. Fully controlled -
 * `value` is {from, to}, `onChange` receives the new {from, to}.
 */
export default function DateRangePicker({ value, onChange, bounds }) {
  const presets = buildPresets(bounds);
  const activePreset = presets.find((p) => p.from === value.from && p.to === value.to);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex gap-2">
        <Input label="From" type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} className="w-40" />
        <Input label="To" type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} className="w-40" />
      </div>
      <div className="flex flex-wrap gap-1.5 pb-0.5">
        {presets.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => onChange({ from: p.from, to: p.to })}
            className={`text-xs px-2.5 py-1.5 rounded-md border transition-colors ${
              activePreset?.label === p.label ? "bg-brand-800 text-white border-brand-800" : "border-ink/15 text-ink/60 hover:bg-brand-50"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
