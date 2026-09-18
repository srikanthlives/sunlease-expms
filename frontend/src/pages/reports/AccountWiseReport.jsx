import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { Card, Table, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft } from "lucide-react";

export default function AccountWiseReport() {
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
    const params = { date_from: range.from, date_to: range.to };
    client.get("/reports/account-wise", { params }).then((res) => setRows(res.data));
  }, [range]);

  const totalPaid = rows ? rows.reduce((s, r) => s + r.total_paid, 0) : 0;
  const totalPayments = rows ? rows.reduce((s, r) => s + r.payment_count, 0) : 0;

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div>
        <h1 className="text-2xl font-display font-semibold">Amount Spent by Account</h1>
        <p className="text-sm text-ink/50 mt-0.5">Total amount paid out through each bank/cash account for the selected date range.</p>
      </div>

      {range && <DateRangePicker value={range} onChange={setRange} bounds={bounds} />}

      {rows && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard label="Total Paid" value={formatMoney(totalPaid)} />
            <StatCard label="Accounts Used" value={rows.length} />
            <StatCard label="Total Payments" value={totalPayments} />
          </div>

          {rows.length > 0 && (
            <Card>
              <h2 className="font-display font-semibold text-lg mb-4">Amount Paid by Account</h2>
              <HorizontalBreakdownList
                data={rows} nameKey="account_name" sortBy="total_paid"
                segments={[{ key: "total_paid", label: "Paid", colorClass: "bg-brand-600" }]}
              />
            </Card>
          )}

          <Card>
            <Table
              columns={[
                { key: "account_name", header: "Account" },
                { key: "account_type", header: "Type" },
                { key: "payment_count", header: "Payments", render: (r) => <span className="tabular">{r.payment_count}</span> },
                { key: "total_paid", header: "Amount Paid", render: (r) => <span className="tabular font-medium">{formatMoney(r.total_paid)}</span> },
              ]}
              rows={rows}
              empty="No payments for this range."
            />
          </Card>
        </>
      )}
    </div>
  );
}
