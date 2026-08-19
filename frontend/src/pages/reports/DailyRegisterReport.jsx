import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { Card, Input, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";

function Row({ label, value, bold }) {
  return (
    <div className={`flex justify-between py-1.5 text-sm ${bold ? "border-t border-ink/10 mt-1 pt-2 font-semibold" : ""}`}>
      <span className="text-ink/60">{label}</span>
      <span className="tabular">{formatMoney(value)}</span>
    </div>
  );
}

function shiftDate(iso, days) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function DailyRegisterReport() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);

  useEffect(() => { client.get("/reports/daily-register", { params: { date } }).then((res) => setData(res.data)); }, [date]);

  const isToday = date === new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-display font-semibold">Daily Register</h1>
          <p className="text-sm text-ink/50 mt-0.5">Everything recorded on a single day.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setDate(shiftDate(date, -1))} className="p-2 rounded-md border border-ink/15 hover:bg-brand-50"><ChevronLeft size={16} /></button>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="max-w-[160px]" />
          <button onClick={() => setDate(shiftDate(date, 1))} disabled={isToday} className="p-2 rounded-md border border-ink/15 hover:bg-brand-50 disabled:opacity-30"><ChevronRight size={16} /></button>
        </div>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Expenses" value={formatMoney(data.expenses.total)} />
            <StatCard label="Total Payments" value={formatMoney(data.payments.total)} tone="ok" />
            <StatCard label="Net Movement" value={formatMoney(data.expenses.total - data.payments.total)} tone="warn" />
            <StatCard label="Date" value={new Date(date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })} />
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <Card>
              <h3 className="font-display font-semibold mb-3">Expenses by Source</h3>
              <Row label="Invoices" value={data.expenses.invoices} />
              <Row label="Direct Expenses" value={data.expenses.direct_expenses} />
              <Row label="Employee Claims" value={data.expenses.employee_claims} />
              <Row label="Total" value={data.expenses.total} bold />
              {data.expenses.total > 0 && (
                <div className="mt-4 pt-4 border-t border-ink/10">
                  <HorizontalBreakdownList
                    data={[{ name: "Expenses", invoices: data.expenses.invoices, direct: data.expenses.direct_expenses, claims: data.expenses.employee_claims }]}
                    nameKey="name" sortBy="invoices"
                    segments={[
                      { key: "invoices", label: "Invoices", colorClass: "bg-brand-500" },
                      { key: "direct", label: "Direct", colorClass: "bg-accent-500" },
                      { key: "claims", label: "Claims", colorClass: "bg-ok" },
                    ]}
                  />
                </div>
              )}
            </Card>
            <Card>
              <h3 className="font-display font-semibold mb-3">Payments by Payee Type</h3>
              <Row label="Vendor Payments" value={data.payments.vendor_payments} />
              <Row label="Employee Payments" value={data.payments.employee_payments} />
              <Row label="Total" value={data.payments.total} bold />
              {data.payments.total > 0 && (
                <div className="mt-4 pt-4 border-t border-ink/10">
                  <HorizontalBreakdownList
                    data={[{ name: "Payments", vendor: data.payments.vendor_payments, employee: data.payments.employee_payments }]}
                    nameKey="name" sortBy="vendor"
                    segments={[
                      { key: "vendor", label: "Vendor", colorClass: "bg-brand-500" },
                      { key: "employee", label: "Employee", colorClass: "bg-accent-500" },
                    ]}
                  />
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
