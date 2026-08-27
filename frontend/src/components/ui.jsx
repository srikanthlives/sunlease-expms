import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

export function Card({ children, className = "", ...props }) {
  return <div className={`ledger-card p-5 ${className}`} {...props}>{children}</div>;
}

export function StatCard({ label, value, sub, tone = "ink" }) {
  const toneClass = {
    ink: "text-ink",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  }[tone];
  return (
    <Card>
      <div className="text-xs uppercase tracking-wide text-ink/50 font-medium">{label}</div>
      <div className={`text-2xl font-display font-semibold mt-1 tabular ${toneClass}`}>{value}</div>
      {sub && <div className="text-xs text-ink/40 mt-1">{sub}</div>}
    </Card>
  );
}

const STATUS_STYLES = {
  PAID: "bg-ok/10 text-ok border-ok/30",
  PARTIALLY_PAID: "bg-warn/10 text-warn border-warn/30",
  UNPAID: "bg-ink/5 text-ink/60 border-ink/15",
  APPROVED: "bg-ok/10 text-ok border-ok/30",
  REJECTED: "bg-danger/10 text-danger border-danger/30",
  PENDING: "bg-accent-500/10 text-accent-600 border-accent-500/30",
  SUBMITTED: "bg-brand-500/10 text-brand-700 border-brand-500/30",
  PENDING_ACCOUNTS_APPROVAL: "bg-accent-500/10 text-accent-600 border-accent-500/30",
  PENDING_ACCOUNTS_REVIEW: "bg-accent-500/10 text-accent-600 border-accent-500/30",
  PENDING_ADMIN_APPROVAL: "bg-brand-500/10 text-brand-700 border-brand-500/30",
  DRAFT: "bg-ink/5 text-ink/50 border-ink/15",
  CANCELLED: "bg-danger/10 text-danger border-danger/30",
  ACTIVE: "bg-ok/10 text-ok border-ok/30",
  RECORDED: "bg-ok/10 text-ok border-ok/30",
};

export function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] || "bg-ink/5 text-ink/60 border-ink/15";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-medium tracking-wide uppercase ${cls}`}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

export function Button({ children, variant = "primary", className = "", ...props }) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-brand-800 text-white hover:bg-brand-900",
    accent: "bg-accent-500 text-white hover:bg-accent-600",
    outline: "border border-ink/15 text-ink hover:bg-ink/5",
    ghost: "text-ink/70 hover:bg-ink/5",
    danger: "bg-danger text-white hover:bg-danger/90",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Input({ label, error, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <input
        className={`w-full rounded-md border border-ink/15 px-3 py-2 text-sm bg-white focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none ${className}`}
        {...props}
      />
      {error && <span className="text-xs text-danger mt-1 block">{error}</span>}
    </label>
  );
}

export function Select({ label, children, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <select
        className={`w-full rounded-md border border-ink/15 px-3 py-2 text-sm bg-white focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none ${className}`}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

export function vendorLabel(vendor) {
  if (!vendor) return "";
  return vendor.location ? `${vendor.vendor_name} (${vendor.location})` : vendor.vendor_name;
}

export function formatMoney(amount) {
  const n = Number(amount || 0);
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Display format everywhere in the app: DD-MMM-YYYY. Accepts an ISO date
// ("2026-08-26"), an ISO datetime, a Date, or null/undefined - never touch
// values feeding a native <input type="date">, which requires ISO.
export function formatDate(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return String(value);
  const day = String(d.getDate()).padStart(2, "0");
  const month = MONTH_ABBR[d.getMonth()];
  const year = d.getFullYear();
  return `${day}-${month}-${year}`;
}

// Same DD-MMM-YYYY date, plus a 24h time - for timestamps (audit logs, edit
// request history) where dropping the time-of-day would lose information.
export function formatDateTime(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${formatDate(d)}, ${hours}:${minutes}`;
}

export function Table({
  columns, rows, keyField = "id", onRowClick, onRowDoubleClick, empty = "No records found.",
  spacious = false, compact = false, footer, stickyHeader = false, maxHeight,
  // Controlled/server-driven sort: pass `sort` ({key, dir}) + `onSortChange`
  // when the caller is fetching already-sorted rows (e.g. sorting the full
  // filtered set across pages via an API param) - clicking a header then
  // calls onSortChange instead of re-sorting `rows` locally. Omit both for
  // the default self-contained client-side sort (sorts whatever `rows` it
  // was given, e.g. just the current page).
  sort: controlledSort, onSortChange,
}) {
  const [internalSort, setInternalSort] = useState(null); // { key, dir: "asc" | "desc" }
  const isControlled = !!onSortChange;
  const sort = isControlled ? controlledSort : internalSort;

  const sortedRows = useMemo(() => {
    if (isControlled) return rows; // caller is responsible for sort order
    if (!sort || !rows) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const accessor = col.sortAccessor || ((r) => r[col.key]);
    const sorted = [...rows].sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
    });
    if (sort.dir === "desc") sorted.reverse();
    return sorted;
  }, [rows, sort, columns, isControlled]);

  if (!rows || rows.length === 0) {
    return <div className="text-sm text-ink/40 py-10 text-center">{empty}</div>;
  }
  const headPad = compact ? "py-1.5 px-2" : spacious ? "py-3 px-4" : "py-2 px-3";
  const cellPad = compact ? "py-1.5 px-2" : spacious ? "py-3.5 px-4" : "py-2.5 px-3";
  const theadClass = stickyHeader
    ? "sticky top-0 z-10 bg-white shadow-[0_1px_0_0_rgba(0,0,0,0.06)]"
    : "border-b border-ink/10";

  // Sticky-left columns (e.g. a frozen "#"/"Date" pair while scrolling
  // right) need position:sticky + an opaque background + a z-index that
  // beats ordinary cells but stays under the sticky header/footer's z-10.
  // Multiple sticky columns stack left-to-right, each offset by the pixel
  // widths declared so far (default 130px per column if unspecified). Each
  // sticky column is also pinned to an exact width - without that, the
  // offset assumed here can drift from the column's real rendered width
  // (auto table layout sizes columns by content) and the frozen columns
  // visually overlap the ones after them once scrolled/clamped.
  let cumulativeLeft = 0;
  const stickyOffsets = new Map();
  for (const c of columns) {
    if (!c.stickyLeft) continue;
    stickyOffsets.set(c.key, cumulativeLeft);
    cumulativeLeft += c.stickyWidth || 130;
  }
  const stickyStyle = (c) => c.stickyLeft
    ? { position: "sticky", left: stickyOffsets.get(c.key), zIndex: 5, width: c.stickyWidth || 130, minWidth: c.stickyWidth || 130, maxWidth: c.stickyWidth || 130 }
    : undefined;
  const stickyHeadStyle = (c) => c.stickyLeft
    ? { position: "sticky", left: stickyOffsets.get(c.key), zIndex: 20, width: c.stickyWidth || 130, minWidth: c.stickyWidth || 130, maxWidth: c.stickyWidth || 130 }
    : undefined;

  function toggleSort(key) {
    const next = (s) => {
      if (!s || s.key !== key) return { key, dir: "asc" };
      if (s.dir === "asc") return { key, dir: "desc" };
      return null;
    };
    if (isControlled) {
      onSortChange(next(sort));
      return;
    }
    setInternalSort(next);
  }

  return (
    <div className="overflow-x-auto" style={stickyHeader ? { maxHeight: maxHeight || "70vh", overflowY: "auto" } : undefined}>
      <table className="w-full text-sm">
        <thead className={theadClass}>
          <tr className="text-left text-xs uppercase tracking-wide text-ink/40">
            {columns.map((c) => (
              <th key={c.key} style={stickyHeadStyle(c)} className={`${headPad} font-medium whitespace-nowrap ${stickyHeader || c.stickyLeft ? "bg-white" : ""} ${c.align === "right" ? "text-right" : ""}`}>
                {c.sortable ? (
                  <button type="button" onClick={() => toggleSort(c.key)} className={`inline-flex items-center gap-1 hover:text-ink/70 ${c.align === "right" ? "flex-row-reverse" : ""}`}>
                    {c.header}
                    {sort?.key === c.key ? (sort.dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />) : <ChevronsUpDown size={12} className="opacity-40" />}
                  </button>
                ) : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={row[keyField]}
              className={`border-b border-ink/5 last:border-0 ${onRowClick || onRowDoubleClick ? "cursor-pointer hover:bg-brand-50" : ""}`}
              onClick={() => onRowClick && onRowClick(row)}
              onDoubleClick={() => onRowDoubleClick && onRowDoubleClick(row)}
            >
              {columns.map((c) => (
                <td key={c.key} style={stickyStyle(c)} className={`${cellPad} align-middle ${c.stickyLeft ? "bg-white" : ""} ${c.align === "right" ? "text-right" : ""}`}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot className={stickyHeader ? "sticky bottom-0 bg-white shadow-[0_-1px_0_0_rgba(0,0,0,0.06)]" : ""}>
            <tr className="border-t-2 border-ink/15 font-medium">
              {columns.map((c) => (
                <td key={c.key} style={stickyHeadStyle(c)} className={`${cellPad} align-middle ${stickyHeader || c.stickyLeft ? "bg-white" : ""} ${c.align === "right" ? "text-right" : ""}`}>
                  {footer[c.key] ?? ""}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
