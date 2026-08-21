import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, Button, Input, Select, formatMoney, vendorLabel } from "../components/ui";
import DateRangePicker from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import EditEntityModal from "../components/EditEntityModal";
import { Plus, X, Trash2, Pencil } from "lucide-react";

const PAYMENT_MODES = ["NEFT", "RTGS", "IMPS", "UPI", "CASH", "CHEQUE"];

export default function Payments() {
  const { user } = useAuth();
  const masters = useMasters();
  const [payments, setPayments] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingPayment, setEditingPayment] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState({ from: "", to: "" });
  const [accountId, setAccountId] = useState("");
  const [paymentMode, setPaymentMode] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const canCreate = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);
  const canEdit = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => setBounds(res.data)).catch(() => {});
  }, []);

  function load() {
    const params = {};
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    if (accountId) params.account_id = accountId;
    if (paymentMode) params.payment_mode = paymentMode;
    if (statusFilter) params.is_cancelled = statusFilter === "CANCELLED";
    client.get("/payments", { params }).then((res) => setPayments(res.data));
  }
  useEffect(load, [range.from, range.to, accountId, paymentMode, statusFilter]);

  function payeeOf(r) {
    if (r.vendor_id) { const v = masters.vendors.find((v) => v.id === r.vendor_id); return v ? vendorLabel(v) : "—"; }
    if (r.employee_id) return masters.employees.find((e) => e.id === r.employee_id)?.employee_name || "—";
    return "Direct Expense";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Payments</h1>
          <p className="text-sm text-ink/50 mt-0.5">Record a payment and allocate it across one or more outstanding expenses.</p>
        </div>
        {canCreate && <Button onClick={() => setShowForm(true)}><Plus size={16} /> New Payment</Button>}
      </div>

      {showForm && <PaymentForm masters={masters} onClose={() => setShowForm(false)} onCreated={() => { setShowForm(false); load(); }} />}

      {editingPayment && (
        <EditEntityModal
          entityType="PAYMENT" entity={editingPayment}
          onClose={() => setEditingPayment(null)}
          onSaved={() => { setEditingPayment(null); load(); }}
        />
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
          <Select label="Account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">All Accounts</option>
            {masters.accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>)}
          </Select>
          <Select label="Mode" value={paymentMode} onChange={(e) => setPaymentMode(e.target.value)}>
            <option value="">All Modes</option>
            {PAYMENT_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Select label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="CANCELLED">Cancelled</option>
          </Select>
        </div>
      </Card>

      <Card>
        <Table
          columns={[
            { key: "payment_number", header: "Payment #" },
            { key: "payment_date", header: "Date" },
            { key: "payee", header: "Payee", render: (r) => payeeOf(r) },
            { key: "account_id", header: "Account", render: (r) => masters.accounts.find((a) => a.id === r.account_id)?.account_name || "—" },
            { key: "payment_mode", header: "Mode" },
            { key: "reference_number", header: "Reference / UTR", render: (r) => r.reference_number || "—" },
            { key: "amount", header: "Amount", render: (r) => <span className="tabular">{formatMoney(r.amount)}</span> },
            { key: "allocations", header: "Allocated To", render: (r) => `${r.allocations.length} expense(s)` },
            { key: "remarks", header: "Remarks", render: (r) => r.remarks || "—" },
            { key: "is_cancelled", header: "Status", render: (r) => r.is_cancelled ? <span className="text-danger text-xs font-medium">CANCELLED</span> : <span className="text-ok text-xs font-medium">ACTIVE</span> },
            {
              key: "attachments", header: "Receipt",
              render: (r) => <Attachments documentType="PAYMENT" paymentId={r.id} compact label="Receipt" />,
            },
            ...(canEdit ? [{
              key: "__edit", header: "",
              render: (r) => !r.is_cancelled && (
                <button type="button" onClick={() => setEditingPayment(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
                  <Pencil size={12} /> Edit
                </button>
              ),
            }] : []),
          ]}
          rows={payments}
        />
      </Card>
    </div>
  );
}

function PaymentForm({ masters, onClose, onCreated }) {
  const [form, setForm] = useState({
    payment_date: new Date().toISOString().slice(0, 10), vendor_id: "", employee_id: "",
    account_id: "", payment_mode: "NEFT", reference_number: "", remarks: "",
  });
  const [payeeType, setPayeeType] = useState("vendor");
  const [outstanding, setOutstanding] = useState([]);
  const [allocations, setAllocations] = useState([]); // {expense_id, allocated_amount}
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (payeeType === "direct") {
      // Direct expenses have no vendor and no employee, so they can't be
      // found via a vendor_id/employee_id filter - fetch broadly and filter
      // client-side to those with neither set.
      client.get("/expenses", { params: { status: "ACTIVE", source_type: "DIRECT_EXPENSE" } }).then((res) => {
        setOutstanding(res.data.filter((e) => e.payment_status !== "PAID" && !e.vendor_id && !e.employee_id));
      });
      return;
    }
    const id = payeeType === "vendor" ? form.vendor_id : form.employee_id;
    if (!id) { setOutstanding([]); return; }
    const params = payeeType === "vendor" ? { vendor_id: id } : { employee_id: id };
    client.get("/expenses", { params: { ...params, status: "ACTIVE" } }).then((res) => {
      setOutstanding(res.data.filter((e) => e.payment_status !== "PAID"));
    });
  }, [form.vendor_id, form.employee_id, payeeType]);

  function addAllocation(expenseId) {
    if (allocations.find((a) => a.expense_id === expenseId)) return;
    const exp = outstanding.find((e) => e.id === expenseId);
    // Prefill with the full outstanding balance - the common case is paying
    // an expense off in one go, and the user can always reduce it.
    setAllocations((a) => [...a, { expense_id: expenseId, allocated_amount: exp ? String(exp.balance_due) : "" }]);
  }
  function updateAllocation(expenseId, amount) {
    setAllocations((a) => a.map((x) => (x.expense_id === expenseId ? { ...x, allocated_amount: amount } : x)));
  }
  function removeAllocation(expenseId) {
    setAllocations((a) => a.filter((x) => x.expense_id !== expenseId));
  }

  const total = allocations.reduce((s, a) => s + Number(a.allocated_amount || 0), 0);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/payments", {
        ...form,
        vendor_id: payeeType === "vendor" ? Number(form.vendor_id) : null,
        employee_id: payeeType === "employee" ? Number(form.employee_id) : null,
        account_id: Number(form.account_id),
        // "direct" payee type has no vendor/employee on the payment itself -
        // the link to the payee (if any) lives on the expense, not here.
        allocations: allocations.map((a) => ({ expense_id: a.expense_id, allocated_amount: Number(a.allocated_amount) })),
      });
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
      <h2 className="font-display font-semibold text-lg mb-4">New Payment</h2>
      <form onSubmit={submit} className="space-y-4 max-w-3xl">
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1.5"><input type="radio" checked={payeeType === "vendor"} onChange={() => { setPayeeType("vendor"); setAllocations([]); }} /> Vendor</label>
          <label className="flex items-center gap-1.5"><input type="radio" checked={payeeType === "employee"} onChange={() => { setPayeeType("employee"); setAllocations([]); }} /> Employee</label>
          <label className="flex items-center gap-1.5"><input type="radio" checked={payeeType === "direct"} onChange={() => { setPayeeType("direct"); setAllocations([]); }} /> Direct Expense (no vendor/employee)</label>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {payeeType === "vendor" && (
            <Select label="Vendor" value={form.vendor_id} onChange={(e) => { set("vendor_id", e.target.value); setAllocations([]); }} required>
              <option value="">Select…</option>
              {masters.vendors.map((v) => <option key={v.id} value={v.id}>{vendorLabel(v)}</option>)}
            </Select>
          )}
          {payeeType === "employee" && (
            <Select label="Employee" value={form.employee_id} onChange={(e) => { set("employee_id", e.target.value); setAllocations([]); }} required>
              <option value="">Select…</option>
              {masters.employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.employee_name}</option>)}
            </Select>
          )}
          <Input label="Payment Date" type="date" value={form.payment_date} onChange={(e) => set("payment_date", e.target.value)} required />
          <Select label="Account" value={form.account_id} onChange={(e) => set("account_id", e.target.value)} required>
            <option value="">Select…</option>
            {masters.accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>)}
          </Select>
          <Select label="Payment Mode" value={form.payment_mode} onChange={(e) => set("payment_mode", e.target.value)}>
            {["NEFT", "RTGS", "IMPS", "UPI", "CASH", "CHEQUE"].map((m) => <option key={m}>{m}</option>)}
          </Select>
          <Input label="Reference / UTR" value={form.reference_number} onChange={(e) => set("reference_number", e.target.value)} />
        </div>

        {outstanding.length > 0 ? (
          <div>
            <div className="text-xs font-medium text-ink/60 mb-2">Outstanding Expenses — click to allocate</div>
            <div className="flex flex-wrap gap-2">
              {outstanding.map((e) => (
                <button type="button" key={e.id} onClick={() => addAllocation(e.id)}
                  className="text-xs border border-ink/15 rounded-md px-2.5 py-1.5 hover:bg-brand-50 disabled:opacity-30"
                  disabled={!!allocations.find((a) => a.expense_id === e.id)}>
                  {e.expense_number} · Balance {formatMoney(e.balance_due)}
                  {e.payment_status === "PARTIALLY_PAID" && (
                    <span className="text-ink/40"> (of {formatMoney(e.total_amount)})</span>
                  )}
                  {" "}<span className="text-ink/40">({e.payment_status})</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-xs text-ink/40">
            {payeeType === "direct"
              ? "No unpaid direct expenses (with no vendor or employee) found."
              : "Select a " + payeeType + " above to see their outstanding expenses."}
          </div>
        )}

        {allocations.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-ink/60">Allocations</div>
            {allocations.map((a) => {
              const exp = outstanding.find((e) => e.id === a.expense_id);
              const balance = Number(exp?.balance_due ?? 0);
              const entered = Number(a.allocated_amount || 0);
              const overAllocated = entered > balance;
              return (
                <div key={a.expense_id} className="bg-brand-50 rounded-md px-3 py-2">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{exp?.expense_number}</div>
                      <div className="text-[11px] text-ink/50">
                        Balance remaining: <span className="tabular font-medium text-ink/70">{formatMoney(balance)}</span>
                        {exp?.payment_status === "PARTIALLY_PAID" && (
                          <span> · already paid {formatMoney(exp.paid_amount)} of {formatMoney(exp.total_amount)}</span>
                        )}
                      </div>
                    </div>
                    <input
                      type="number" step="0.01" placeholder="Amount" value={a.allocated_amount}
                      max={balance} min="0"
                      onChange={(e) => updateAllocation(a.expense_id, e.target.value)}
                      className={`w-32 rounded border px-2 py-1 text-sm tabular ${overAllocated ? "border-danger text-danger" : "border-ink/15"}`}
                    />
                    <button type="button" onClick={() => removeAllocation(a.expense_id)} className="text-ink/30 hover:text-danger"><Trash2 size={15} /></button>
                  </div>
                  {overAllocated && (
                    <div className="text-[11px] text-danger mt-1">Exceeds the outstanding balance of {formatMoney(balance)}</div>
                  )}
                </div>
              );
            })}
            <div className="text-sm text-right text-ink/60">Total: <span className="tabular font-semibold text-ink">{formatMoney(total)}</span></div>
          </div>
        )}

        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy || allocations.length === 0}>{busy ? "Saving…" : "Save Payment"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
