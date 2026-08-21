import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, StatusBadge, Button, Input, Select, formatMoney, vendorLabel } from "../components/ui";
import DateRangePicker from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import EditEntityModal from "../components/EditEntityModal";
import SubCategorySelect from "../components/SubCategorySelect";
import { Plus, X, Pencil, ChevronLeft, ChevronRight } from "lucide-react";

const SOURCE_TYPES = ["DIRECT_EXPENSE", "INVOICE", "EMPLOYEE_CLAIM"];
const PAYMENT_STATUSES = ["UNPAID", "PARTIALLY_PAID", "PAID"];
const PAGE_SIZES = [25, 50, 100];

export default function Expenses() {
  const { user } = useAuth();
  const masters = useMasters();
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingExpense, setEditingExpense] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState({ from: "", to: "" });
  const [sourceType, setSourceType] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState(null); // { key, dir } - key matches a backend sort_by name
  const canCreate = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);
  const canEdit = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => setBounds(res.data)).catch(() => {});
  }, []);

  function filterParams() {
    const params = {};
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    if (sourceType) params.source_type = sourceType;
    if (paymentStatus) params.payment_status = paymentStatus;
    return params;
  }

  function load() {
    const listParams = { ...filterParams(), page, page_size: pageSize };
    if (sort) { listParams.sort_by = sort.key; listParams.sort_dir = sort.dir; }
    client.get("/expenses", { params: listParams }).then((res) => setExpenses(res.data));
    client.get("/expenses/summary", { params: filterParams() }).then((res) => setSummary(res.data));
  }
  useEffect(load, [range.from, range.to, sourceType, paymentStatus, page, pageSize, sort]);
  // Any filter or sort change should snap back to page 1 - a stale deep page
  // number against a smaller/differently-ordered result set would render an
  // empty or confusing table.
  useEffect(() => { setPage(1); }, [range.from, range.to, sourceType, paymentStatus, pageSize, sort]);

  const totalPages = summary ? Math.max(1, Math.ceil(summary.count / pageSize)) : 1;

  const vendorName = (id) => { const v = masters.vendors.find((v) => v.id === id); return v ? vendorLabel(v) : "—"; };
  const employeeName = (id) => masters.employees.find((e) => e.id === id)?.employee_name || "—";
  const projectName = (id) => masters.projects.find((p) => p.id === id)?.name || "—";
  const categoryName = (id) => masters.categories.find((c) => c.id === id)?.name || "—";
  const subCategoryName = (id) => masters.subCategories.find((s) => s.id === id)?.name || "—";
  function payeeOf(r) {
    if (r.source_type === "INVOICE") return vendorName(r.vendor_id);
    if (r.source_type === "EMPLOYEE_CLAIM") return employeeName(r.employee_id);
    return r.supplier_name || "—";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Expenses</h1>
          <p className="text-sm text-ink/50 mt-0.5">Direct expenses, plus expenses generated from invoices and claims.</p>
        </div>
        {canCreate && (
          <Button onClick={() => setShowForm(true)}><Plus size={16} /> New Direct Expense</Button>
        )}
      </div>

      {showForm && (
        <ExpenseForm
          masters={masters}
          onClose={() => setShowForm(false)}
          onCreated={() => { setShowForm(false); load(); }}
        />
      )}

      {editingExpense && (
        <EditEntityModal
          entityType="EXPENSE" entity={editingExpense}
          onClose={() => setEditingExpense(null)}
          onSaved={() => { setEditingExpense(null); load(); }}
        />
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
          <Select label="Source" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="">All Sources</option>
            {SOURCE_TYPES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
          <Select label="Payment" value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)}>
            <option value="">All Payment Statuses</option>
            {PAYMENT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
        </div>
      </Card>

      <Card>
        <Table
          compact
          stickyHeader
          sort={sort}
          onSortChange={setSort}
          columns={[
            { key: "expense_number", header: "Expense #", stickyLeft: true, stickyWidth: 140, render: (r) => <span className="whitespace-nowrap">{r.expense_number}</span> },
            {
              key: "expense_date", header: "Date", stickyLeft: true, stickyWidth: 110, sortable: true,
              render: (r) => <span className="whitespace-nowrap">{r.expense_date}</span>,
            },
            {
              key: "source_type", header: "Source", sortable: true,
              render: (r) => <span className="text-xs text-ink/50 whitespace-nowrap">{r.source_type.replace(/_/g, " ")}</span>,
            },
            {
              key: "payee", header: "Vendor / Employee / Supplier", sortable: true,
              render: (r) => { const text = payeeOf(r); return <span title={text} className="block max-w-[180px] truncate">{text}</span>; },
            },
            {
              key: "bill_number", header: "Voucher / Bill No",
              render: (r) => { const text = r.bill_number || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            {
              key: "project_id", header: "Project", sortable: true,
              render: (r) => { const text = projectName(r.project_id); return <span title={text} className="block max-w-[180px] truncate">{text}</span>; },
            },
            { key: "category_id", header: "Head", sortable: true, render: (r) => categoryName(r.category_id) },
            {
              key: "sub_category_id", header: "Sub-Head", sortable: true,
              render: (r) => r.sub_category_id ? subCategoryName(r.sub_category_id) : "—",
            },
            { key: "base_amount", header: "Base", align: "right", render: (r) => <span className="tabular">{formatMoney(r.base_amount)}</span> },
            { key: "gst_amount", header: "GST", align: "right", render: (r) => <span className="tabular">{formatMoney(r.gst_amount)}</span> },
            {
              key: "total_amount", header: "Amount", sortable: true, align: "right",
              render: (r) => <span className="tabular">{formatMoney(r.total_amount)}</span>,
            },
            {
              key: "paid_amount", header: "Paid", sortable: true, align: "right",
              render: (r) => <span className="tabular">{formatMoney(r.paid_amount)}</span>,
            },
            {
              key: "balance_due", header: "Balance", sortable: true, align: "right",
              render: (r) => <span className="tabular">{formatMoney(r.balance_due)}</span>,
            },
            {
              key: "description", header: "Description",
              render: (r) => {
                const text = r.description || "";
                return text ? (
                  <span title={text} className="block whitespace-nowrap overflow-hidden text-ellipsis" style={{ width: "30ch" }}>
                    {text}
                  </span>
                ) : "—";
              },
            },
            {
              key: "payment_status", header: "Payment", sortable: true,
              render: (r) => <span className="whitespace-nowrap"><StatusBadge status={r.payment_status} /></span>,
            },
            { key: "status", header: "Status", render: (r) => <span className="whitespace-nowrap"><StatusBadge status={r.status} /></span> },
            {
              key: "attachments", header: "Proof / Bill",
              render: (r) => (
                <Attachments
                  documentType="EXPENSE" expenseId={r.id} compact
                  label={r.source_type === "INVOICE" ? "Invoice/Bill" : r.source_type === "EMPLOYEE_CLAIM" ? "Proof" : "Attach"}
                />
              ),
            },
            ...(canEdit ? [{
              key: "__edit", header: "",
              render: (r) => r.status === "ACTIVE" && r.source_type === "DIRECT_EXPENSE" && (
                <button type="button" onClick={() => setEditingExpense(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
                  <Pencil size={12} /> Edit
                </button>
              ),
            }] : []),
          ]}
          rows={expenses}
          footer={summary && {
            expense_number: `${summary.count} expense(s)`,
            base_amount: <span className="tabular">{formatMoney(summary.base_amount)}</span>,
            gst_amount: <span className="tabular">{formatMoney(summary.gst_amount)}</span>,
            total_amount: <span className="tabular">{formatMoney(summary.total_amount)}</span>,
            paid_amount: <span className="tabular">{formatMoney(summary.paid_amount)}</span>,
            balance_due: <span className="tabular">{formatMoney(summary.balance_due)}</span>,
          }}
        />

        {summary && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-ink/10 text-sm text-ink/60">
            <div className="flex items-center gap-2">
              <span>Rows per page</span>
              <div className="w-20">
                <Select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                  {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span>
                Page {page} of {totalPages} · {summary.count} total
              </span>
              <div className="flex gap-1">
                <button
                  type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="p-1.5 rounded-md border border-ink/15 disabled:opacity-30 hover:bg-brand-50"
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  type="button" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1.5 rounded-md border border-ink/15 disabled:opacity-30 hover:bg-brand-50"
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function ExpenseForm({ masters, onClose, onCreated }) {
  const [form, setForm] = useState({
    expense_date: new Date().toISOString().slice(0, 10),
    project_id: "", category_id: "", sub_category_id: "",
    supplier_name: "", bill_number: "",
    description: "", base_amount: "", gst_amount: "0", other_amount: "0",
    pay_immediately: false, payment_date: new Date().toISOString().slice(0, 10),
    account_id: "", payment_mode: "NEFT", reference_number: "", remarks: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        project_id: form.project_id || null,
        sub_category_id: form.sub_category_id || null,
        supplier_name: form.supplier_name || null,
        bill_number: form.bill_number || null,
        category_id: Number(form.category_id),
        base_amount: Number(form.base_amount),
        gst_amount: Number(form.gst_amount || 0),
        other_amount: Number(form.other_amount || 0),
        account_id: form.pay_immediately ? Number(form.account_id) : null,
      };
      await client.post("/expenses", payload);
      onCreated();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative">
      <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
      <h2 className="font-display font-semibold text-lg mb-4">New Direct Expense</h2>
      <form onSubmit={submit} className="space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Date" type="date" value={form.expense_date} onChange={(e) => set("expense_date", e.target.value)} required />
          <Select label="Project" value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
            <option value="">— none —</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select label="Expense Head" value={form.category_id} onChange={(e) => { set("category_id", e.target.value); set("sub_category_id", ""); }} required>
            <option value="">Select…</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <SubCategorySelect categoryId={form.category_id} value={form.sub_category_id} onChange={(v) => set("sub_category_id", v)} />
          <Input label="Supplier Name" value={form.supplier_name} onChange={(e) => set("supplier_name", e.target.value)} />
          <Input label="Voucher / Bill No" value={form.bill_number} onChange={(e) => set("bill_number", e.target.value)} />
        </div>
        <Input label="Description" value={form.description} onChange={(e) => set("description", e.target.value)} />
        <div className="grid grid-cols-3 gap-4">
          <Input label="Base Amount" type="number" step="0.01" value={form.base_amount} onChange={(e) => set("base_amount", e.target.value)} required />
          <Input label="GST Amount" type="number" step="0.01" value={form.gst_amount} onChange={(e) => set("gst_amount", e.target.value)} />
          <Input label="Other Amount" type="number" step="0.01" value={form.other_amount} onChange={(e) => set("other_amount", e.target.value)} />
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.pay_immediately} onChange={(e) => set("pay_immediately", e.target.checked)} />
          Pay now
        </label>

        {form.pay_immediately && (
          <div className="grid grid-cols-3 gap-4 bg-brand-50 rounded-md p-4">
            <Select label="Account" value={form.account_id} onChange={(e) => set("account_id", e.target.value)} required>
              <option value="">Select…</option>
              {masters.accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>)}
            </Select>
            <Select label="Payment Mode" value={form.payment_mode} onChange={(e) => set("payment_mode", e.target.value)}>
              {["NEFT", "RTGS", "IMPS", "UPI", "CASH", "CHEQUE"].map((m) => <option key={m}>{m}</option>)}
            </Select>
            <Input label="Reference / UTR" value={form.reference_number} onChange={(e) => set("reference_number", e.target.value)} />
          </div>
        )}

        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save Expense"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
