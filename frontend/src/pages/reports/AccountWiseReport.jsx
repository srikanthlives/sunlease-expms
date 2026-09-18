import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { useMasters } from "../../hooks/useMasters";
import { Card, Table, Select, StatCard, formatMoney } from "../../components/ui";
import { HorizontalBreakdownList } from "../../components/charts";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft } from "lucide-react";

const SOURCE_TYPES = ["EXPENSE", "INVOICE", "EMPLOYEE_CLAIM"];
const PAYMENT_STATUSES = ["UNPAID", "PARTIALLY_PAID", "PAID"];

export default function AccountWiseReport() {
  const masters = useMasters();
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(null);
  const [projectId, setProjectId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("");
  const [rows, setRows] = useState(null);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => {
      setBounds(res.data);
      const allTime = buildPresets(res.data).find((p) => p.label === "All Time");
      setRange({ from: allTime.from, to: allTime.to });
    });
  }, []);

  useEffect(() => { setSubCategoryId(""); }, [categoryId]);

  useEffect(() => {
    if (!range) return;
    const params = { date_from: range.from, date_to: range.to };
    if (projectId) params.project_id = projectId;
    if (categoryId) params.category_id = categoryId;
    if (subCategoryId) params.sub_category_id = subCategoryId;
    if (sourceType) params.source_type = sourceType;
    if (paymentStatus) params.payment_status = paymentStatus;
    client.get("/reports/account-wise", { params }).then((res) => setRows(res.data));
  }, [range, projectId, categoryId, subCategoryId, sourceType, paymentStatus]);

  const totalPaid = rows ? rows.reduce((s, r) => s + r.total_paid, 0) : 0;
  const totalPayments = rows ? rows.reduce((s, r) => s + r.payment_count, 0) : 0;

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div>
        <h1 className="text-2xl font-display font-semibold">Amount Spent by Account</h1>
        <p className="text-sm text-ink/50 mt-0.5">Total amount paid out through each bank/cash account for the selected date range.</p>
      </div>

      {range && (
        <Card>
          <div className="flex flex-wrap items-end gap-4">
            <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
          </div>
          <div className="flex flex-wrap items-end gap-4 mt-4 pt-4 border-t border-ink/10">
            <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-44">
              <option value="">All Projects</option>
              {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Select label="Source" value={sourceType} onChange={(e) => setSourceType(e.target.value)} className="w-44">
              <option value="">All Sources</option>
              {SOURCE_TYPES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
            <Select label="Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-44">
              <option value="">All Heads</option>
              {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Sub-Head" value={subCategoryId} onChange={(e) => setSubCategoryId(e.target.value)} disabled={!categoryId} className="w-44">
              <option value="">All Sub-Heads</option>
              {masters.subCategories.filter((s) => String(s.category_id) === String(categoryId)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <Select label="Payment" value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)} className="w-44">
              <option value="">All Payment Statuses</option>
              {PAYMENT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
        </Card>
      )}

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
              empty="No payments for this filter."
            />
          </Card>
        </>
      )}
    </div>
  );
}
