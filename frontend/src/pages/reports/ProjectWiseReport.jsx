import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { Card, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft, ChevronDown, ChevronRight, Loader2 } from "lucide-react";

const COLS = [
  { key: "project_name", header: "Project" },
  { key: "invoices", header: "Invoices" },
  { key: "direct_expenses", header: "Direct" },
  { key: "employee_claims", header: "Claims" },
  { key: "total_expense", header: "Total" },
  { key: "payments", header: "Paid" },
  { key: "outstanding", header: "Outstanding" },
];

function ProjectTreeTable({ rows, range }) {
  const [expandedProjects, setExpandedProjects] = useState(() => new Set());
  const [expandedCategories, setExpandedCategories] = useState(() => new Set());
  const [trees, setTrees] = useState({}); // project_id -> breakdown response
  const [loading, setLoading] = useState(() => new Set());

  // A new date range invalidates every cached breakdown - collapse and refetch on next expand.
  useEffect(() => {
    setExpandedProjects(new Set());
    setExpandedCategories(new Set());
    setTrees({});
  }, [range]);

  function toggleProject(projectId) {
    setExpandedProjects((s) => {
      const next = new Set(s);
      if (next.has(projectId)) {
        next.delete(projectId);
        return next;
      }
      next.add(projectId);
      if (!trees[projectId]) {
        setLoading((l) => new Set(l).add(projectId));
        client
          .get(`/reports/project-wise/${projectId}/category-breakdown`, { params: { date_from: range.from, date_to: range.to } })
          .then((res) => setTrees((t) => ({ ...t, [projectId]: res.data })))
          .finally(() => setLoading((l) => { const n = new Set(l); n.delete(projectId); return n; }));
      }
      return next;
    });
  }

  function toggleCategory(projectId, categoryId) {
    const key = `${projectId}:${categoryId}`;
    setExpandedCategories((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const cellPad = "py-2.5 px-3";

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-ink/10">
          <tr className="text-left text-xs uppercase tracking-wide text-ink/40">
            {COLS.map((c) => (
              <th key={c.key} className={`${cellPad} font-medium whitespace-nowrap ${c.key !== "project_name" ? "text-right" : ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isOpen = expandedProjects.has(row.project_id);
            const isLoading = loading.has(row.project_id);
            const tree = trees[row.project_id];
            return (
              <Fragment key={row.project_id}>
                <tr
                  className="border-b border-ink/5 cursor-pointer hover:bg-brand-50"
                  onClick={() => toggleProject(row.project_id)}
                >
                  <td className={`${cellPad} align-middle font-medium`}>
                    <span className="inline-flex items-center gap-1.5">
                      {isOpen ? <ChevronDown size={14} className="text-ink/40 shrink-0" /> : <ChevronRight size={14} className="text-ink/40 shrink-0" />}
                      {row.project_name}
                    </span>
                  </td>
                  <td className={`${cellPad} align-middle text-right tabular`}>{formatMoney(row.invoices)}</td>
                  <td className={`${cellPad} align-middle text-right tabular`}>{formatMoney(row.direct_expenses)}</td>
                  <td className={`${cellPad} align-middle text-right tabular`}>{formatMoney(row.employee_claims)}</td>
                  <td className={`${cellPad} align-middle text-right tabular font-medium`}>{formatMoney(row.total_expense)}</td>
                  <td className={`${cellPad} align-middle text-right tabular`}>{formatMoney(row.payments)}</td>
                  <td className={`${cellPad} align-middle text-right tabular`}>{formatMoney(row.outstanding)}</td>
                </tr>

                {isOpen && isLoading && (
                  <tr key={`${row.project_id}-loading`} className="border-b border-ink/5 bg-brand-50/40">
                    <td colSpan={COLS.length} className="py-3 px-3 pl-9 text-xs text-ink/40">
                      <span className="inline-flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> Loading category breakdown…</span>
                    </td>
                  </tr>
                )}

                {isOpen && tree && tree.categories.length === 0 && (
                  <tr key={`${row.project_id}-empty`} className="border-b border-ink/5 bg-brand-50/40">
                    <td colSpan={COLS.length} className="py-3 px-3 pl-9 text-xs text-ink/40">No expenses recorded for this project in this range.</td>
                  </tr>
                )}

                {isOpen && tree && tree.categories.map((cat) => {
                  const catKey = `${row.project_id}:${cat.category_id}`;
                  const catOpen = expandedCategories.has(catKey);
                  const pct = tree.categories.reduce((s, c) => s + c.total, 0) > 0
                    ? (cat.total / tree.categories.reduce((s, c) => s + c.total, 0)) * 100
                    : 0;
                  return (
                    <Fragment key={catKey}>
                      <tr
                        className="border-b border-ink/5 bg-brand-50/40 cursor-pointer hover:bg-brand-50"
                        onClick={() => toggleCategory(row.project_id, cat.category_id)}
                      >
                        <td className="py-2 px-3 pl-9 align-middle">
                          <span className="inline-flex items-center gap-1.5 text-ink/80">
                            {catOpen ? <ChevronDown size={13} className="text-ink/40 shrink-0" /> : <ChevronRight size={13} className="text-ink/40 shrink-0" />}
                            {cat.category_name}
                            <span className="text-[11px] text-ink/40 tabular">{pct.toFixed(0)}%</span>
                          </span>
                        </td>
                        <td colSpan={3}></td>
                        <td className="py-2 px-3 align-middle text-right tabular font-medium">{formatMoney(cat.total)}</td>
                        <td colSpan={2}></td>
                      </tr>
                      {catOpen && cat.sub_categories.map((sub) => (
                        <tr key={`${catKey}:${sub.sub_category_id}`} className="border-b border-ink/5 bg-brand-50/20">
                          <td className="py-1.5 px-3 pl-16 align-middle text-ink/60 text-xs">{sub.sub_category_name}</td>
                          <td colSpan={3}></td>
                          <td className="py-1.5 px-3 align-middle text-right tabular text-xs">{formatMoney(sub.total)}</td>
                          <td colSpan={2}></td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function ProjectWiseReport() {
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(null);
  const [rows, setRows] = useState(null);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => {
      setBounds(res.data);
      const allTime = buildPresets(res.data).find((p) => p.label === "All Time");
      setRange({ from: allTime.from, to: allTime.to });
    });
  }, []);

  useEffect(() => {
    if (!range) return;
    client.get("/reports/project-wise", { params: { date_from: range.from, date_to: range.to } }).then((res) => setRows(res.data));
  }, [range]);

  const withActivity = rows ? rows.filter((r) => r.total_expense > 0) : [];
  const totalExpense = withActivity.reduce((s, r) => s + r.total_expense, 0);
  const totalOutstanding = withActivity.reduce((s, r) => s + r.outstanding, 0);

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div>
        <h1 className="text-2xl font-display font-semibold">Project-wise Report</h1>
        <p className="text-sm text-ink/50 mt-0.5">Spend and outstanding balance by project.</p>
      </div>

      {range && <DateRangePicker value={range} onChange={setRange} bounds={bounds} />}

      {rows && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard label="Active Projects" value={withActivity.length} />
            <StatCard label="Total Expense" value={formatMoney(totalExpense)} />
            <StatCard label="Total Outstanding" value={formatMoney(totalOutstanding)} tone="warn" />
          </div>

          {withActivity.length > 0 && (
            <Card>
              <h2 className="font-display font-semibold text-lg mb-4">Spend Composition</h2>
              <HorizontalBreakdownList
                data={withActivity} nameKey="project_name" sortBy="total_expense"
                segments={[
                  { key: "invoices", label: "Invoices", colorClass: "bg-brand-500" },
                  { key: "direct_expenses", label: "Direct", colorClass: "bg-accent-500" },
                  { key: "employee_claims", label: "Claims", colorClass: "bg-ok" },
                ]}
              />
            </Card>
          )}

          <Card>
            <p className="text-xs text-ink/40 mb-2">Click a project row to expand its expense breakdown by category and sub-category.</p>
            <ProjectTreeTable rows={rows} range={range} />
          </Card>
        </>
      )}
    </div>
  );
}
