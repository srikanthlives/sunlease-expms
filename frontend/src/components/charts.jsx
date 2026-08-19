import { formatMoney } from "./ui";

/**
 * Simple vertical grouped bar chart, CSS/SVG-free (matches the style already
 * used on the financial dashboard). `series` is [{key, label, colorClass}].
 */
export function VerticalBarChart({ data, series, xKey, height = 180, xLabel }) {
  const max = Math.max(1, ...data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0)));
  return (
    <div>
      <div className="flex items-end gap-2 overflow-x-auto pb-1" style={{ height }}>
        {data.map((d, i) => (
          <div key={d[xKey] ?? i} className="flex-1 min-w-[28px] flex flex-col items-center justify-end gap-1 h-full">
            <div className="flex-1 flex items-end gap-0.5 w-full justify-center">
              {series.map((s) => (
                <div
                  key={s.key}
                  className={`w-2.5 rounded-t ${s.colorClass}`}
                  style={{ height: `${(Number(d[s.key]) / max) * 100}%`, minHeight: 2 }}
                  title={`${s.label}: ${formatMoney(d[s.key])}`}
                />
              ))}
            </div>
            <div className="text-[10px] text-ink/40 tabular whitespace-nowrap">{xLabel ? xLabel(d) : d[xKey]}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-4 mt-3 text-xs text-ink/50">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5"><span className={`w-2.5 h-2.5 rounded-sm ${s.colorClass}`} /> {s.label}</div>
        ))}
      </div>
    </div>
  );
}

/**
 * Horizontal proportional bar per row - e.g. paid vs outstanding for each
 * vendor/employee/project, sorted by total descending.
 */
export function HorizontalBreakdownList({ data, nameKey, segments, sortBy }) {
  const sorted = [...data].sort((a, b) => Number(b[sortBy] ?? 0) - Number(a[sortBy] ?? 0));
  const max = Math.max(1, ...sorted.map((d) => segments.reduce((s, seg) => s + Number(d[seg.key] || 0), 0)));
  return (
    <div className="space-y-3">
      {sorted.map((d, i) => {
        const total = segments.reduce((s, seg) => s + Number(d[seg.key] || 0), 0);
        return (
          <div key={d[nameKey] ?? i}>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-ink/70">{d[nameKey]}</span>
              <span className="tabular font-medium">{formatMoney(total)}</span>
            </div>
            <div className="h-2 bg-ink/5 rounded-full overflow-hidden flex">
              {segments.map((seg) => (
                <div
                  key={seg.key}
                  className={seg.colorClass}
                  style={{ width: `${(Number(d[seg.key] || 0) / max) * 100}%` }}
                  title={`${seg.label}: ${formatMoney(d[seg.key])}`}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
