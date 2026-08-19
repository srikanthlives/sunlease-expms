import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { Card, Table, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft } from "lucide-react";

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
            <Table
              columns={[
                { key: "project_name", header: "Project" },
                { key: "invoices", header: "Invoices", render: (r) => <span className="tabular">{formatMoney(r.invoices)}</span> },
                { key: "direct_expenses", header: "Direct", render: (r) => <span className="tabular">{formatMoney(r.direct_expenses)}</span> },
                { key: "employee_claims", header: "Claims", render: (r) => <span className="tabular">{formatMoney(r.employee_claims)}</span> },
                { key: "total_expense", header: "Total", render: (r) => <span className="tabular font-medium">{formatMoney(r.total_expense)}</span> },
                { key: "payments", header: "Paid", render: (r) => <span className="tabular">{formatMoney(r.payments)}</span> },
                { key: "outstanding", header: "Outstanding", render: (r) => <span className="tabular">{formatMoney(r.outstanding)}</span> },
              ]}
              rows={rows}
            />
          </Card>
        </>
      )}
    </div>
  );
}
