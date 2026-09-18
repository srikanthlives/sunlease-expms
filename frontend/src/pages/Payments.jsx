import { useEffect, useRef, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, Button, IconButton, Input, Select, formatMoney, formatDate, vendorLabel } from "../components/ui";
import DateRangePicker, { defaultMonthRange } from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import EditEntityModal from "../components/EditEntityModal";
import { Plus, X, Trash2, Pencil, ShieldCheck, ShieldOff, Columns3 } from "lucide-react";

const PAYMENT_MODES = ["NEFT", "RTGS", "IMPS", "UPI", "CASH", "CHEQUE"];

// Columns the user can show/hide via the "Columns" picker. payment_number,
// payment_date (both sticky-left) and __actions stay mandatory - excluded
// here so they're always rendered regardless of what's hidden.
const TOGGLEABLE_COLUMNS = [
  { key: "payee", label: "Payee" },
  { key: "account_id", label: "Account" },
  { key: "payment_mode", label: "Mode" },
  { key: "reference_number", label: "Reference / UTR" },
  { key: "amount", label: "Amount" },
  { key: "allocations", label: "Allocated To" },
  { key: "remarks", label: "Remarks" },
  { key: "is_cancelled", label: "Status" },
  { key: "is_verified", label: "Verified" },
  { key: "attachments", label: "Receipt" },
];
const HIDDEN_COLUMNS_STORAGE_KEY = "expms_payments_hidden_columns";

function ColumnsPicker({ hidden, onToggle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <Button variant="outline" onClick={() => setOpen((o) => !o)}>
        <Columns3 size={16} /> Columns
      </Button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-64 max-h-80 overflow-y-auto bg-white border border-ink/15 rounded-md shadow-lg py-2">
          {TOGGLEABLE_COLUMNS.map((c) => (
            <label key={c.key} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-brand-50 cursor-pointer">
              <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => onToggle(c.key)} />
              {c.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Payments() {
  const { user } = useAuth();
  const masters = useMasters();
  const [payments, setPayments] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingPayment, setEditingPayment] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(defaultMonthRange);
  const [accountId, setAccountId] = useState("");
  const [paymentMode, setPaymentMode] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [projectId, setProjectId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [hiddenCols, setHiddenCols] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE_KEY) || "[]")); } catch { return new Set(); }
  });
  const canCreate = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);
  const canEdit = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"].includes(user?.role);
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);

  function toggleColumn(key) {
    setHiddenCols((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key); else next.add(key);
      localStorage.setItem(HIDDEN_COLUMNS_STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  async function toggleVerify(r) {
    await client.post(`/payments/${r.id}/${r.is_verified ? "unverify" : "verify"}`);
    load();
  }

  async function deletePayment(r) {
    if (!window.confirm(`Delete ${r.payment_number}? The expense(s) it was allocated to will fall back to unpaid / partially paid. This cannot be undone.`)) return;
    try {
      await client.delete(`/payments/${r.id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }

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
    if (projectId) params.project_id = projectId;
    if (categoryId) params.category_id = categoryId;
    if (subCategoryId) params.sub_category_id = subCategoryId;
    client.get("/payments", { params }).then((res) => setPayments(res.data));
  }
  useEffect(load, [range.from, range.to, accountId, paymentMode, statusFilter, projectId, categoryId, subCategoryId]);
  // Selecting a different Head clears any Sub-Head that no longer belongs to it.
  useEffect(() => { setSubCategoryId(""); }, [categoryId]);

  function payeeOf(r) {
    if (r.vendor_id) { const v = masters.vendors.find((v) => v.id === r.vendor_id); return v ? vendorLabel(v) : "—"; }
    if (r.employee_id) return masters.employees.find((e) => e.id === r.employee_id)?.employee_name || "—";
    return "Expense";
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
          <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">All Projects</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select label="Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">All Heads</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select label="Sub-Head" value={subCategoryId} onChange={(e) => setSubCategoryId(e.target.value)} disabled={!categoryId}>
            <option value="">All Sub-Heads</option>
            {masters.subCategories.filter((s) => String(s.category_id) === String(categoryId)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
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
        <div className="flex justify-end mb-2">
          <ColumnsPicker hidden={hiddenCols} onToggle={toggleColumn} />
        </div>
        <Table
          compact
          stickyHeader
          columns={[
            { key: "payment_number", header: "Payment #", stickyLeft: true, stickyWidth: 130, render: (r) => <span className="whitespace-nowrap">{r.payment_number}</span> },
            {
              key: "payment_date", header: "Date", stickyLeft: true, stickyWidth: 110, sortable: true,
              render: (r) => <span className="whitespace-nowrap">{formatDate(r.payment_date)}</span>,
            },
            {
              key: "payee", header: "Payee", sortable: true,
              render: (r) => { const text = payeeOf(r); return <span title={text} className="block max-w-[180px] truncate">{text}</span>; },
            },
            {
              key: "account_id", header: "Account", sortable: true,
              sortAccessor: (r) => masters.accounts.find((a) => a.id === r.account_id)?.account_name || "",
              render: (r) => { const text = masters.accounts.find((a) => a.id === r.account_id)?.account_name || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            { key: "payment_mode", header: "Mode", sortable: true, render: (r) => <span className="whitespace-nowrap">{r.payment_mode}</span> },
            {
              key: "reference_number", header: "Reference / UTR",
              render: (r) => { const text = r.reference_number || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            {
              key: "amount", header: "Amount", sortable: true, align: "right",
              render: (r) => <span className="tabular whitespace-nowrap">{formatMoney(r.amount)}</span>,
            },
            {
              key: "allocations", header: "Allocated To",
              render: (r) => {
                const text = r.allocations.map((a) => a.expense_number || `#${a.expense_id}`).join(", ");
                return <span title={text} className="block max-w-[200px] truncate">{text}</span>;
              },
            },
            {
              key: "remarks", header: "Remarks",
              render: (r) => { const text = r.remarks || "—"; return <span title={text} className="block max-w-[160px] truncate">{text}</span>; },
            },
            {
              key: "is_cancelled", header: "Status", sortable: true,
              render: (r) => r.is_cancelled
                ? <span className="text-danger text-xs font-medium whitespace-nowrap">CANCELLED</span>
                : <span className="text-ok text-xs font-medium whitespace-nowrap">ACTIVE</span>,
            },
            {
              key: "is_verified", header: "Verified", sortable: true,
              render: (r) => r.is_verified
                ? <span className="text-xs text-ok whitespace-nowrap" title={r.verified_by_name ? `Verified by ${r.verified_by_name}` : ""}>✓ Verified</span>
                : <span className="text-xs text-ink/40 whitespace-nowrap">—</span>,
            },
            {
              key: "attachments", header: "Receipt",
              render: (r) => <Attachments documentType="PAYMENT" paymentId={r.id} compact label="Receipt" canDelete={isAdmin || !r.is_verified} />,
            },
            ...(canEdit || isAdmin ? [{
              key: "__actions", header: "",
              render: (r) => {
                if (r.is_cancelled) return null;
                const canDelete = isAdmin || !r.is_verified;
                return (
                  <div className="flex items-center gap-0.5 whitespace-nowrap">
                    {canEdit && <IconButton icon={Pencil} title="Edit" onClick={() => setEditingPayment(r)} />}
                    {canDelete && <IconButton icon={Trash2} title="Delete" tone="danger" onClick={() => deletePayment(r)} />}
                    {isAdmin && (
                      <IconButton
                        icon={r.is_verified ? ShieldOff : ShieldCheck}
                        title={r.is_verified ? "Unverify" : "Verify"}
                        tone={r.is_verified ? "muted" : "ok"}
                        onClick={() => toggleVerify(r)}
                      />
                    )}
                  </div>
                );
              },
            }] : []),
          ].filter((c) => ["payment_number", "payment_date", "__actions"].includes(c.key) || !hiddenCols.has(c.key))}
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
      // Direct expenses AND recurring-expense bills set up with no
      // vendor/employee (payee_type DIRECT, e.g. a plain utility bill) have
      // no vendor and no employee, so they can't be found via a
      // vendor_id/employee_id filter - fetch broadly (no source_type
      // restriction) and filter client-side to those with neither set.
      client.get("/expenses", { params: { status: "ACTIVE" } }).then((res) => {
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
          <label className="flex items-center gap-1.5"><input type="radio" checked={payeeType === "direct"} onChange={() => { setPayeeType("direct"); setAllocations([]); }} /> Direct / Recurring Expense (no vendor/employee)</label>
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
                  {e.expense_number}
                  {e.source_type === "EXPENSE" && e.source_id != null && <span className="text-brand-700"> (Recurring)</span>}
                  {e.supplier_name && <span className="text-ink/50"> · {e.supplier_name}</span>}
                  {" · Balance "}{formatMoney(e.balance_due)}
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
              ? "No unpaid direct or recurring expenses (with no vendor or employee) found."
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
