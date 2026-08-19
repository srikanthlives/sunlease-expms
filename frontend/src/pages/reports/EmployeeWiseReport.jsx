import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { useMasters } from "../../hooks/useMasters";
import { Card, Table, Select, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft } from "lucide-react";

export default function EmployeeWiseReport() {
  const masters = useMasters();
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(null);
  const [projectId, setProjectId] = useState("");
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
    const params = { date_from: range.from, date_to: range.to };
    if (projectId) params.project_id = projectId;
    client.get("/reports/employee-wise", { params }).then((res) => setRows(res.data));
  }, [range, projectId]);

  const totalClaimed = rows ? rows.reduce((s, r) => s + r.claimed, 0) : 0;
  const totalPaid = rows ? rows.reduce((s, r) => s + r.paid, 0) : 0;
  const totalOutstanding = rows ? rows.reduce((s, r) => s + r.outstanding, 0) : 0;

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-display font-semibold">Employee-wise Report</h1>
          <p className="text-sm text-ink/50 mt-0.5">Claims, approvals, and reimbursement status per employee.</p>
        </div>
        <Select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-52">
          <option value="">All Projects</option>
          {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {range && <DateRangePicker value={range} onChange={setRange} bounds={bounds} />}

      {rows && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard label="Total Claimed" value={formatMoney(totalClaimed)} />
            <StatCard label="Total Reimbursed" value={formatMoney(totalPaid)} tone="ok" />
            <StatCard label="Total Outstanding" value={formatMoney(totalOutstanding)} tone="warn" />
          </div>

          {rows.length > 0 && (
            <Card>
              <h2 className="font-display font-semibold text-lg mb-4">Reimbursed vs Outstanding by Employee</h2>
              <HorizontalBreakdownList
                data={rows} nameKey="employee_name" sortBy="claimed"
                segments={[
                  { key: "paid", label: "Reimbursed", colorClass: "bg-ok" },
                  { key: "outstanding", label: "Outstanding", colorClass: "bg-warn" },
                ]}
              />
            </Card>
          )}

          <Card>
            <Table
              columns={[
                { key: "employee_name", header: "Employee" },
                { key: "total_claims", header: "Claims" },
                { key: "claimed", header: "Claimed", render: (r) => <span className="tabular">{formatMoney(r.claimed)}</span> },
                { key: "approved", header: "Approved", render: (r) => <span className="tabular">{formatMoney(r.approved)}</span> },
                { key: "paid", header: "Reimbursed", render: (r) => <span className="tabular">{formatMoney(r.paid)}</span> },
                { key: "outstanding", header: "Outstanding", render: (r) => <span className="tabular font-medium">{formatMoney(r.outstanding)}</span> },
              ]}
              rows={rows}
              empty="No claims for this range."
            />
          </Card>
        </>
      )}
    </div>
  );
}
