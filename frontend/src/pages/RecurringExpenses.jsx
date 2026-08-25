import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { Card, Table, Button, Input, Select, StatusBadge, formatMoney, vendorLabel } from "../components/ui";
import { Plus, X, Pencil, Power } from "lucide-react";

const FREQUENCIES = [
  { value: "WEEKLY", label: "Weekly" },
  { value: "BIWEEKLY", label: "Bi-Weekly" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "HALF_YEARLY", label: "Half-Yearly" },
  { value: "ANNUALLY", label: "Annually" },
];

const PAYEE_TYPES = [
  { value: "DIRECT", label: "Direct Expense" },
  { value: "VENDOR", label: "Vendor Expense" },
  { value: "EMPLOYEE", label: "Employee Expense" },
];

function emptyForm() {
  return {
    name: "", frequency: "MONTHLY", amount_type: "FIXED", fixed_amount: "",
    lead_days: 7, due_in_days: "", payee_type: "DIRECT", supplier_name: "",
    project_id: "", vendor_id: "", employee_id: "",
    category_id: "", sub_category_id: "", description: "", next_occurrence_date: "", is_active: true,
  };
}

function TemplateForm({ masters, editing, onClose, onSaved }) {
  const [form, setForm] = useState(editing ? {
    ...editing,
    fixed_amount: editing.fixed_amount ?? "",
    due_in_days: editing.due_in_days ?? "",
    supplier_name: editing.supplier_name ?? "",
    project_id: editing.project_id ?? "", vendor_id: editing.vendor_id ?? "", employee_id: editing.employee_id ?? "",
    sub_category_id: editing.sub_category_id ?? "",
  } : emptyForm());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const subCats = masters.subCategories.filter((s) => String(s.category_id) === String(form.category_id));

  function set(key, value) { setForm((s) => ({ ...s, [key]: value })); }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        name: form.name,
        frequency: form.frequency,
        amount_type: form.amount_type,
        fixed_amount: form.amount_type === "FIXED" ? Number(form.fixed_amount) : null,
        lead_days: Number(form.lead_days),
        due_in_days: form.due_in_days === "" ? null : Number(form.due_in_days),
        payee_type: form.payee_type,
        supplier_name: form.payee_type === "DIRECT" ? form.supplier_name : null,
        project_id: Number(form.project_id),
        vendor_id: form.payee_type === "VENDOR" ? Number(form.vendor_id) : null,
        employee_id: form.payee_type === "EMPLOYEE" ? Number(form.employee_id) : null,
        category_id: Number(form.category_id),
        sub_category_id: form.sub_category_id || null,
        description: form.description || null,
        next_occurrence_date: form.next_occurrence_date,
        is_active: form.is_active ?? true,
      };
      if (editing) {
        await client.put(`/recurring-expenses/${editing.id}`, payload);
      } else {
        await client.post("/recurring-expenses", payload);
      }
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative">
      <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
      <h2 className="font-display font-semibold text-lg mb-4">{editing ? "Edit" : "New"} Recurring Expense</h2>
      <form onSubmit={submit} className="space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Name" required value={form.name} onChange={(e) => set("name", e.target.value)}
            placeholder="e.g. Office Internet Bill" />
          <Select label="Frequency" value={form.frequency} onChange={(e) => set("frequency", e.target.value)}>
            {FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </Select>

          <Select label="Amount Type" value={form.amount_type} onChange={(e) => set("amount_type", e.target.value)}>
            <option value="FIXED">Fixed Amount</option>
            <option value="OPEN">Open Amount (varies each cycle)</option>
          </Select>
          {form.amount_type === "FIXED" && (
            <Input label="Fixed Amount" type="number" step="0.01" required
              value={form.fixed_amount} onChange={(e) => set("fixed_amount", e.target.value)} />
          )}

          <Input label="Next Bill Date" type="date" required
            value={form.next_occurrence_date} onChange={(e) => set("next_occurrence_date", e.target.value)} />
          <Input label="Days Before Bill Date to Send for Approval" type="number" min="0" required
            value={form.lead_days} onChange={(e) => set("lead_days", e.target.value)} />

          <Input label="Bill Due In (days after bill date, optional)" type="number" min="0"
            value={form.due_in_days} onChange={(e) => set("due_in_days", e.target.value)} />
          <Select label="Project" required value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
            <option value="">— Select —</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>

          <Select label="Expense Type" value={form.payee_type} onChange={(e) => set("payee_type", e.target.value)}>
            {PAYEE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </Select>
          <div />

          {form.payee_type === "DIRECT" && (
            <Input label="Supplier / Payee Name" required value={form.supplier_name}
              onChange={(e) => set("supplier_name", e.target.value)} />
          )}
          {form.payee_type === "VENDOR" && (
            <Select label="Vendor" required value={form.vendor_id} onChange={(e) => set("vendor_id", e.target.value)}>
              <option value="">— Select —</option>
              {masters.vendors
                .filter((v) => !form.project_id || !v.project_ids?.length || v.project_ids.includes(Number(form.project_id)))
                .map((v) => <option key={v.id} value={v.id}>{vendorLabel(v)}</option>)}
            </Select>
          )}
          {form.payee_type === "EMPLOYEE" && (
            <Select label="Employee" required value={form.employee_id} onChange={(e) => set("employee_id", e.target.value)}>
              <option value="">— Select —</option>
              {masters.employees.map((e) => <option key={e.id} value={e.id}>{e.employee_name}</option>)}
            </Select>
          )}

          <Select label="Expense Category" required value={form.category_id}
            onChange={(e) => set("category_id", e.target.value)}>
            <option value="">— Select —</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select label="Sub-Category" value={form.sub_category_id} onChange={(e) => set("sub_category_id", e.target.value)}>
            <option value="">— None —</option>
            {subCats.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </div>
        <Input label="Description / Notes" value={form.description || ""} onChange={(e) => set("description", e.target.value)} />

        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : editing ? "Save Changes" : "Create"}</Button>
      </form>
    </Card>
  );
}

function TemplatesTab({ masters }) {
  const [rows, setRows] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  function load() { client.get("/recurring-expenses").then((res) => setRows(res.data)); }
  useEffect(load, []);

  async function toggleActive(row) {
    await client.post(`/recurring-expenses/${row.id}/${row.is_active ? "deactivate" : "activate"}`);
    load();
  }

  const categoryName = (id) => masters.categories.find((c) => c.id === id)?.name || "—";
  const projectName = (id) => masters.projects.find((p) => p.id === id)?.name || "—";
  const payeeName = (row) => {
    if (row.payee_type === "VENDOR") return vendorLabel(masters.vendors.find((v) => v.id === row.vendor_id)) || "—";
    if (row.payee_type === "EMPLOYEE") return masters.employees.find((e) => e.id === row.employee_id)?.employee_name || "—";
    return row.supplier_name || "—";
  };

  const columns = [
    { key: "name", header: "Name", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "frequency", header: "Frequency", render: (r) => FREQUENCIES.find((f) => f.value === r.frequency)?.label || r.frequency },
    { key: "amount_type", header: "Amount", render: (r) => r.amount_type === "FIXED" ? formatMoney(r.fixed_amount) : <span className="text-ink/50 italic">Open</span> },
    { key: "payee", header: "Payee", render: payeeName },
    { key: "project_id", header: "Project", render: (r) => projectName(r.project_id) },
    { key: "category_id", header: "Category", render: (r) => categoryName(r.category_id) },
    { key: "next_occurrence_date", header: "Next Bill Date" },
    { key: "is_active", header: "Status", render: (r) => <StatusBadge status={r.is_active ? "ACTIVE" : "CANCELLED"} /> },
    {
      key: "__actions", header: "", render: (r) => (
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => { setEditing(r); setShowForm(true); }} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
            <Pencil size={12} /> Edit
          </button>
          <button type="button" onClick={() => toggleActive(r)} className="text-xs inline-flex items-center gap-1 text-ink/60 hover:underline">
            <Power size={12} /> {r.is_active ? "Deactivate" : "Activate"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New Recurring Expense</Button>
      </div>
      {showForm && (
        <TemplateForm masters={masters} editing={editing} onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); load(); }} />
      )}
      <Card>
        <Table columns={columns} rows={rows} empty="No recurring expenses set up yet." />
      </Card>
    </div>
  );
}

export default function RecurringExpenses() {
  const masters = useMasters();

  if (masters.loading) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Recurring Expenses</h1>
        <p className="text-sm text-ink/50 mt-0.5">Rent, bills and other regularly-repeating expenses — set up once, and each cycle's bill gets sent for approval automatically ahead of its due date.</p>
      </div>
      <TemplatesTab masters={masters} />
    </div>
  );
}
