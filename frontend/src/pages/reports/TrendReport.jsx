import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { useMasters } from "../../hooks/useMasters";
import { Card, Table, Select, StatCard, formatMoney } from "../../components/ui";
import { VerticalBarChart } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft } from "lucide-react";

export default function TrendReport() {
  const masters = useMasters();
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(null);
  const [projectId, setProjectId] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => {
      setBounds(res.data);
      // Default to "Last 6 Months" (matches the API's own default range).
      const presets = buildPresets(res.data);
      const last6 = presets.find((p) => p.label === "Last 6 Months");
      setRange({ from: last6.from, to: last6.to });
    });
  }, []);

  useEffect(() => {
    if (!range) return;
    const params = { date_from: range.from, date_to: range.to };
    if (projectId) params.project_id = projectId;
    client.get("/reports/trend", { params }).then((res) => setData(res.data));
  }, [range, projectId]);

  const chartData = data ? data.months.map((m) => ({ ...m, label: m.label.slice(2) })) : [];
  const spanMonths = data ? data.months.length : 0;

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-display font-semibold">Trend Report</h1>
          <p className="text-sm text-ink/50 mt-0.5">Expense and payment trend over any date range you choose.</p>
        </div>
        <Select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-52">
          <option value="">All Projects</option>
          {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {range && <DateRangePicker value={range} onChange={setRange} bounds={bounds} />}

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Expense" value={formatMoney(data.totals.total_expense)} />
            <StatCard label="Total Payments" value={formatMoney(data.totals.payments)} tone="ok" />
            <StatCard label="Outstanding" value={formatMoney(data.totals.total_expense - data.totals.payments)} tone="warn" />
            <StatCard label="Monthly Average" value={formatMoney(spanMonths ? data.totals.total_expense / spanMonths : 0)} />
          </div>

          <Card>
            <h2 className="font-display font-semibold text-lg mb-4">Expenses vs Payments</h2>
            {chartData.length === 0 ? (
              <div className="text-sm text-ink/40 py-8 text-center">No activity in this range.</div>
            ) : (
              <VerticalBarChart
                data={chartData} xKey="label" height={200}
                series={[
                  { key: "total_expense", label: "Expenses", colorClass: "bg-brand-500" },
                  { key: "payments", label: "Payments", colorClass: "bg-accent-500" },
                ]}
              />
            )}
          </Card>

          {chartData.length > 0 && (
            <Card>
              <h2 className="font-display font-semibold text-lg mb-4">Expense Composition</h2>
              <VerticalBarChart
                data={chartData} xKey="label" height={180}
                series={[
                  { key: "invoices", label: "Invoices", colorClass: "bg-brand-500" },
                  { key: "direct_expenses", label: "Direct", colorClass: "bg-accent-500" },
                  { key: "employee_claims", label: "Claims", colorClass: "bg-ok" },
                ]}
              />
            </Card>
          )}

          <Card>
            <h2 className="font-display font-semibold text-lg mb-4">Month-by-Month Detail</h2>
            <Table
              columns={[
                { key: "label", header: "Month" },
                { key: "invoices", header: "Invoices", render: (r) => <span className="tabular">{formatMoney(r.invoices)}</span> },
                { key: "direct_expenses", header: "Direct", render: (r) => <span className="tabular">{formatMoney(r.direct_expenses)}</span> },
                { key: "employee_claims", header: "Claims", render: (r) => <span className="tabular">{formatMoney(r.employee_claims)}</span> },
                { key: "total_expense", header: "Total Expense", render: (r) => <span className="tabular font-medium">{formatMoney(r.total_expense)}</span> },
                { key: "payments", header: "Payments", render: (r) => <span className="tabular">{formatMoney(r.payments)}</span> },
                { key: "outstanding", header: "Outstanding", render: (r) => <span className="tabular">{formatMoney(r.outstanding)}</span> },
              ]}
              rows={data.months}
              empty="No activity in this range."
            />
          </Card>
        </>
      )}
    </div>
  );
}
