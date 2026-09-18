import { useEffect, useRef, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useMasters } from "../hooks/useMasters";
import { Card, Table, Button, Input, Select, StatusBadge, formatMoney, formatDate, vendorLabel } from "../components/ui";
import { Plus, X, Pencil, Power, ShieldCheck, ShieldOff, Trash2, ChevronLeft, ChevronRight, Columns3, FileDown } from "lucide-react";

const PAGE_SIZES = [25, 50, 100];

// Columns the user can show/hide via the "Columns" picker. name and
// __actions stay mandatory - excluded here so they're always rendered
// regardless of what's hidden.
const TOGGLEABLE_COLUMNS = [
  { key: "frequency", label: "Frequency" },
  { key: "amount_type", label: "Amount" },
  { key: "payee", label: "Payee" },
  { key: "project_id", label: "Project" },
  { key: "category_id", label: "Head" },
  { key: "sub_category_id", label: "Sub-Head" },
  { key: "description", label: "Description" },
  { key: "next_occurrence_date", label: "Next Bill Date" },
  { key: "is_active", label: "Status" },
  { key: "is_verified", label: "Verified" },
];
const HIDDEN_COLUMNS_STORAGE_KEY = "expms_recurring_expenses_hidden_columns";

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

const FREQUENCIES = [
  { value: "WEEKLY", label: "Weekly" },
  { value: "BIWEEKLY", label: "Bi-Weekly" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "HALF_YEARLY", label: "Half-Yearly" },
  { value: "ANNUALLY", label: "Annually" },
];

const PAYEE_TYPES = [
  { value: "DIRECT", label: "Expense" },
  { value: "VENDOR", label: "Vendor Expense (Invoice)" },
];

function emptyForm() {
  return {
    name: "", frequency: "MONTHLY", amount_type: "FIXED", fixed_amount: "",
    lead_days: 7, due_in_days: "", payee_type: "DIRECT", supplier_name: "",
    project_id: "", vendor_id: "",
    category_id: "", sub_category_id: "", description: "", next_occurrence_date: "", is_active: true,
  };
}

function TemplateForm({ masters, editing, onClose, onSaved }) {
  const [form, setForm] = useState(editing ? {
    ...editing,
    fixed_amount: editing.fixed_amount ?? "",
    due_in_days: editing.due_in_days ?? "",
    supplier_name: editing.supplier_name ?? "",
    project_id: editing.project_id ?? "", vendor_id: editing.vendor_id ?? "",
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
            <div>
              <Input label="Supplier / Payee Name" required value={form.supplier_name}
                onChange={(e) => set("supplier_name", e.target.value)} list="supplier-name-options" />
              <datalist id="supplier-name-options">
                {masters.vendors.map((v) => <option key={v.id} value={v.vendor_name}>{vendorLabel(v)}</option>)}
              </datalist>
              <p className="text-xs text-ink/40 mt-1">Pick a vendor from the suggestions, or type a payee name manually.</p>
            </div>
          )}
          {form.payee_type === "VENDOR" && (
            <Select label="Vendor" required value={form.vendor_id} onChange={(e) => set("vendor_id", e.target.value)}>
              <option value="">— Select —</option>
              {masters.vendors
                .filter((v) => !form.project_id || !v.project_ids?.length || v.project_ids.includes(Number(form.project_id)))
                .map((v) => <option key={v.id} value={v.id}>{vendorLabel(v)}</option>)}
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
  const { user } = useAuth();
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [exporting, setExporting] = useState(false);
  const [hiddenCols, setHiddenCols] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE_KEY) || "[]")); } catch { return new Set(); }
  });

  function toggleColumn(key) {
    setHiddenCols((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key); else next.add(key);
      localStorage.setItem(HIDDEN_COLUMNS_STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  function load() { client.get("/recurring-expenses").then((res) => setRows(res.data)); }
  useEffect(load, []);
  useEffect(() => { setPage(1); }, [pageSize, rows.length]);

  async function downloadPdf() {
    const visibleColumns = TOGGLEABLE_COLUMNS.map((c) => c.key).filter((k) => !hiddenCols.has(k));
    setExporting(true);
    try {
      const res = await client.get("/recurring-expenses/export-pdf", {
        params: { columns: visibleColumns.join(",") },
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `recurring-expenses-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  async function toggleActive(row) {
    await client.post(`/recurring-expenses/${row.id}/${row.is_active ? "deactivate" : "activate"}`);
    load();
  }

  async function toggleVerified(row) {
    await client.post(`/recurring-expenses/${row.id}/${row.is_verified ? "unverify" : "verify"}`);
    load();
  }

  async function deleteTemplate(row) {
    if (!window.confirm(`Delete "${row.name}"? This cannot be undone.`)) return;
    setError("");
    try {
      await client.delete(`/recurring-expenses/${row.id}`);
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const categoryName = (id) => masters.categories.find((c) => c.id === id)?.name || "—";
  const subCategoryName = (id) => masters.subCategories.find((s) => s.id === id)?.name || "—";
  const projectName = (id) => masters.projects.find((p) => p.id === id)?.name || "—";
  const payeeName = (row) => {
    if (row.payee_type === "VENDOR") return vendorLabel(masters.vendors.find((v) => v.id === row.vendor_id)) || "—";
    return row.supplier_name || "—";
  };

  const columns = [
    { key: "name", header: "Name", sortable: true, render: (r) => <span className="font-medium">{r.name}</span> },
    {
      key: "frequency", header: "Frequency", sortable: true,
      sortAccessor: (r) => FREQUENCIES.find((f) => f.value === r.frequency)?.label || r.frequency,
      render: (r) => FREQUENCIES.find((f) => f.value === r.frequency)?.label || r.frequency,
    },
    {
      key: "amount_type", header: "Amount", sortable: true,
      sortAccessor: (r) => r.amount_type === "FIXED" ? Number(r.fixed_amount) : -1,
      render: (r) => r.amount_type === "FIXED" ? formatMoney(r.fixed_amount) : <span className="text-ink/50 italic">Open</span>,
    },
    { key: "payee", header: "Payee", sortable: true, sortAccessor: payeeName, render: payeeName },
    { key: "project_id", header: "Project", sortable: true, sortAccessor: (r) => projectName(r.project_id), render: (r) => projectName(r.project_id) },
    { key: "category_id", header: "Head", sortable: true, sortAccessor: (r) => categoryName(r.category_id), render: (r) => categoryName(r.category_id) },
    {
      key: "sub_category_id", header: "Sub-Head", sortable: true,
      sortAccessor: (r) => r.sub_category_id ? subCategoryName(r.sub_category_id) : "",
      render: (r) => r.sub_category_id ? subCategoryName(r.sub_category_id) : "—",
    },
    { key: "description", header: "Description", render: (r) => <span title={r.description || ""} className="block max-w-[220px] truncate text-ink/60">{r.description || "—"}</span> },
    { key: "next_occurrence_date", header: "Next Bill Date", sortable: true, render: (r) => formatDate(r.next_occurrence_date) },
    { key: "is_active", header: "Status", sortable: true, render: (r) => <StatusBadge status={r.is_active ? "ACTIVE" : "CANCELLED"} /> },
    {
      key: "is_verified", header: "Verified", sortable: true,
      render: (r) => r.is_verified
        ? <span className="text-xs text-ok whitespace-nowrap" title={r.verified_by_name ? `Verified by ${r.verified_by_name}` : ""}>✓ Verified</span>
        : <span className="text-xs text-ink/40">—</span>,
    },
    {
      key: "__actions", header: "", render: (r) => {
        const canEdit = isAdmin || !r.is_verified;
        return (
          <div className="flex items-center gap-3">
            {canEdit && (
              <button type="button" onClick={() => { setEditing(r); setShowForm(true); }} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
                <Pencil size={12} /> Edit
              </button>
            )}
            {canEdit && (
              <button type="button" onClick={() => deleteTemplate(r)} className="text-xs inline-flex items-center gap-1 text-danger hover:underline">
                <Trash2 size={12} /> Delete
              </button>
            )}
            <button type="button" onClick={() => toggleActive(r)} className="text-xs inline-flex items-center gap-1 text-ink/60 hover:underline">
              <Power size={12} /> {r.is_active ? "Deactivate" : "Activate"}
            </button>
            {isAdmin && (
              <button
                type="button" onClick={() => toggleVerified(r)}
                className={`text-xs inline-flex items-center gap-1 hover:underline ${r.is_verified ? "text-ink/60" : "text-ok"}`}
              >
                {r.is_verified ? <ShieldOff size={12} /> : <ShieldCheck size={12} />} {r.is_verified ? "Unverify" : "Verify"}
              </button>
            )}
          </div>
        );
      },
    },
  ];

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageRows = rows.slice((page - 1) * pageSize, (page - 1) * pageSize + pageSize);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New Recurring Expense</Button>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      {showForm && (
        <TemplateForm masters={masters} editing={editing} onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); load(); }} />
      )}
      <Card>
        <div className="flex justify-end gap-2 mb-2">
          <Button variant="outline" onClick={downloadPdf} disabled={exporting}>
            <FileDown size={16} /> {exporting ? "Preparing…" : "Download PDF"}
          </Button>
          <ColumnsPicker hidden={hiddenCols} onToggle={toggleColumn} />
        </div>
        <Table
          compact
          stickyHeader
          columns={columns.filter((c) => ["name", "__actions"].includes(c.key) || !hiddenCols.has(c.key))}
          rows={pageRows}
          empty="No recurring expenses set up yet."
        />

        {rows.length > 0 && (
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
              <span>Page {page} of {totalPages} · {rows.length} total</span>
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
