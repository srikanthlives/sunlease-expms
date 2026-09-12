import { ChevronLeft, ChevronRight } from "lucide-react";
import { Input, IconButton } from "./ui";

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

// Default range for list screens (Expenses/Payments/Invoices/Claims) -
// matches the "This Month" preset below, so the page loads already showing
// the current month's activity instead of everything ever recorded.
export function defaultMonthRange() {
  const today = isoToday();
  return { from: today.slice(0, 8) + "01", to: today };
}

// Normalizes to the 1st of the month `delta` months away from `fromStr`
// (defaulting to today when the range is unbounded, e.g. Claim Approvals).
function stepMonth(fromStr, delta) {
  const d = new Date(fromStr || isoToday());
  d.setDate(1);
  d.setMonth(d.getMonth() + delta);
  return d;
}
// The full {from, to} for the month a Date falls in, clamped so `to` never
// runs past today (there's nothing to show beyond "now").
function monthRange(d) {
  const today = isoToday();
  const from = d.toISOString().slice(0, 10);
  const end = new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
  return { from, to: end > today ? today : end };
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

  // Next is disabled once stepping forward would start a month beyond
  // today - there's nothing to show there yet.
  const nextMonthStart = stepMonth(value.from, 1);
  const nextDisabled = nextMonthStart.toISOString().slice(0, 10) > isoToday();

  return (
    <div className="flex flex-wrap items-end gap-3">
      <IconButton
        icon={ChevronLeft} title="Previous Month" bordered
        onClick={() => onChange(monthRange(stepMonth(value.from, -1)))}
      />
      <div className="flex gap-2">
        <Input label="From" type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} className="w-40" />
        <Input label="To" type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} className="w-40" />
      </div>
      <IconButton
        icon={ChevronRight} title="Next Month" bordered disabled={nextDisabled}
        onClick={() => onChange(monthRange(nextMonthStart))}
      />
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
