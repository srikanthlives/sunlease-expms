import { useEffect, useRef, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, StatusBadge, Button, IconButton, Input, Textarea, Select, formatMoney, formatDate, vendorLabel } from "../components/ui";
import DateRangePicker, { defaultMonthRange } from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import EditEntityModal from "../components/EditEntityModal";
import SubCategorySelect from "../components/SubCategorySelect";
import { Plus, X, Pencil, Trash2, ShieldCheck, ShieldOff, ChevronLeft, ChevronRight, Columns3, FileDown } from "lucide-react";

const INVOICE_STATUSES = ["RECORDED", "CANCELLED"];
const PAGE_SIZES = [25, 50, 100];

// Columns the user can show/hide via the "Columns" picker. invoice_number,
// invoice_date (both sticky-left) and __actions stay mandatory - excluded
// here so they're always rendered regardless of what's hidden.
const TOGGLEABLE_COLUMNS = [
  { key: "vendor_id", label: "Vendor" },
  { key: "po_number", label: "PO Number" },
  { key: "due_date", label: "Due Date" },
  { key: "project_id", label: "Project" },
  { key: "category_id", label: "Head" },
  { key: "sub_category_id", label: "Sub-Head" },
  { key: "description", label: "Description" },
  { key: "taxable_amount", label: "Taxable" },
  { key: "tax", label: "Tax" },
  { key: "total_amount", label: "Amount" },
  { key: "status", label: "Status" },
  { key: "is_verified", label: "Verified" },
  { key: "attachments", label: "Invoice / Bill" },
];
const HIDDEN_COLUMNS_STORAGE_KEY = "expms_invoices_hidden_columns";

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

export default function Invoices() {
  const { user } = useAuth();
  const masters = useMasters();
  const [invoices, setInvoices] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(defaultMonthRange);
  const [projectId, setProjectId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState(null);
  const [hiddenCols, setHiddenCols] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE_KEY) || "[]")); } catch { return new Set(); }
  });
  const [exporting, setExporting] = useState(false);
  const canCreate = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS", "SUPER_ACCOUNTS"].includes(user?.role);
  const canEdit = ["ADMIN", "SUPER_ADMIN", "ACCOUNTS", "SUPER_ACCOUNTS"].includes(user?.role);
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);

  async function toggleVerify(r) {
    await client.post(`/invoices/${r.id}/${r.is_verified ? "unverify" : "verify"}`);
    load();
  }

  async function deleteInvoice(r) {
    if (!window.confirm(`Delete ${r.invoice_number}? Its linked expense will be deleted too. This cannot be undone.`)) return;
    try {
      await client.delete(`/invoices/${r.id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }

  function toggleColumn(key) {
    setHiddenCols((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key); else next.add(key);
      localStorage.setItem(HIDDEN_COLUMNS_STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => setBounds(res.data)).catch(() => {});
  }, []);

  function filterParams() {
    const params = {};
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    if (projectId) params.project_id = projectId;
    if (vendorId) params.vendor_id = vendorId;
    if (categoryId) params.category_id = categoryId;
    if (subCategoryId) params.sub_category_id = subCategoryId;
    if (invoiceStatus) params.status_ = invoiceStatus;
    return params;
  }

  function load() {
    const listParams = { ...filterParams(), page, page_size: pageSize };
    if (sort) { listParams.sort_by = sort.key; listParams.sort_dir = sort.dir; }
    client.get("/invoices", { params: listParams }).then((res) => setInvoices(res.data));
    client.get("/invoices/summary", { params: filterParams() }).then((res) => setSummary(res.data));
  }
  useEffect(load, [range.from, range.to, projectId, vendorId, categoryId, subCategoryId, invoiceStatus, page, pageSize, sort]);
  useEffect(() => { setPage(1); }, [range.from, range.to, projectId, vendorId, categoryId, subCategoryId, invoiceStatus, pageSize, sort]);
  useEffect(() => { setSubCategoryId(""); }, [categoryId]);

  async function downloadPdf() {
    const visibleColumns = TOGGLEABLE_COLUMNS.map((c) => c.key).filter((k) => k !== "attachments" && !hiddenCols.has(k));
    setExporting(true);
    try {
      const res = await client.get("/invoices/export-pdf", {
        params: { ...filterParams(), columns: visibleColumns.join(",") },
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoices-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  const totalPages = summary ? Math.max(1, Math.ceil(summary.count / pageSize)) : 1;

  const vendorName = (id) => { const v = masters.vendors.find((v) => v.id === id); return v ? vendorLabel(v) : id; };
  const projectName = (id) => masters.projects.find((p) => p.id === id)?.name || "—";
  const categoryName = (id) => masters.categories.find((c) => c.id === id)?.name || "—";
  const subCategoryName = (id) => masters.subCategories.find((s) => s.id === id)?.name || "—";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Supplier Invoices</h1>
          <p className="text-sm text-ink/50 mt-0.5">Record vendor invoices; pay in full or in parts over time.</p>
        </div>
        {canCreate && <Button onClick={() => setShowForm(true)}><Plus size={16} /> New Invoice</Button>}
      </div>

      {showForm && <InvoiceForm masters={masters} onClose={() => setShowForm(false)} onCreated={() => { setShowForm(false); load(); }} />}

      {editingInvoice && (
        <EditEntityModal
          entityType="INVOICE" entity={editingInvoice}
          onClose={() => setEditingInvoice(null)}
          onSaved={() => { setEditingInvoice(null); load(); }}
        />
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
        </div>
        <div className="flex flex-wrap items-end gap-4 mt-4 pt-4 border-t border-ink/10">
          <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-44">
            <option value="">All Projects</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select label="Vendor" value={vendorId} onChange={(e) => setVendorId(e.target.value)} className="w-44">
            <option value="">All Vendors</option>
            {masters.vendors.map((v) => <option key={v.id} value={v.id}>{vendorLabel(v)}</option>)}
          </Select>
          <Select label="Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-44">
            <option value="">All Heads</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select label="Sub-Head" value={subCategoryId} onChange={(e) => setSubCategoryId(e.target.value)} disabled={!categoryId} className="w-44">
            <option value="">All Sub-Heads</option>
            {masters.subCategories.filter((s) => String(s.category_id) === String(categoryId)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select label="Status" value={invoiceStatus} onChange={(e) => setInvoiceStatus(e.target.value)} className="w-44">
            <option value="">All Statuses</option>
            {INVOICE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
      </Card>

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
          sort={sort}
          onSortChange={setSort}
          columns={[
            { key: "invoice_number", header: "Invoice #", stickyLeft: true, stickyWidth: 130, sortable: true },
            {
              key: "vendor_id", header: "Vendor", sortable: true,
              render: (r) => { const text = vendorName(r.vendor_id); return <span title={text} className="block max-w-[200px] truncate">{text}</span>; },
            },
            {
              key: "po_number", header: "PO Number",
              render: (r) => { const text = r.po_number || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            { key: "invoice_date", header: "Date", sortable: true, render: (r) => <span className="whitespace-nowrap">{formatDate(r.invoice_date)}</span> },
            { key: "due_date", header: "Due Date", sortable: true, render: (r) => <span className="whitespace-nowrap">{r.due_date ? formatDate(r.due_date) : "—"}</span> },
            {
              key: "project_id", header: "Project", sortable: true,
              render: (r) => { const text = projectName(r.project_id); return <span title={text} className="block max-w-[160px] truncate">{text}</span>; },
            },
            { key: "category_id", header: "Head", sortable: true, render: (r) => r.category_id ? categoryName(r.category_id) : "—" },
            { key: "sub_category_id", header: "Sub-Head", sortable: true, render: (r) => r.sub_category_id ? subCategoryName(r.sub_category_id) : "—" },
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
            { key: "taxable_amount", header: "Taxable", sortable: true, align: "right", render: (r) => <span className="tabular">{formatMoney(r.taxable_amount)}</span> },
            {
              key: "tax", header: "Tax", align: "right",
              render: (r) => <span className="tabular">{formatMoney(Number(r.cgst) + Number(r.sgst) + Number(r.igst) + Number(r.other_tax))}</span>,
            },
            { key: "total_amount", header: "Amount", sortable: true, align: "right", render: (r) => <span className="tabular">{formatMoney(r.total_amount)}</span> },
            { key: "status", header: "Status", sortable: true, render: (r) => <StatusBadge status={r.status} /> },
            {
              key: "is_verified", header: "Verified",
              render: (r) => r.is_verified
                ? <span className="text-xs text-ok whitespace-nowrap" title={r.verified_by_name ? `Verified by ${r.verified_by_name}` : ""}>✓ Verified</span>
                : <span className="text-xs text-ink/40">—</span>,
            },
            {
              key: "attachments", header: "Invoice / Bill",
              render: (r) => <Attachments documentType="INVOICE" invoiceId={r.id} compact label="Invoice/Bill" canDelete={isAdmin || !r.is_verified} />,
            },
            ...(canEdit || isAdmin ? [{
              key: "__actions", header: "",
              render: (r) => {
                if (r.status !== "RECORDED") return null;
                const canDelete = isAdmin || !r.is_verified;
                return (
                  <div className="flex items-center gap-0.5 whitespace-nowrap">
                    {canEdit && <IconButton icon={Pencil} title="Edit" onClick={() => setEditingInvoice(r)} />}
                    {canDelete && <IconButton icon={Trash2} title="Delete" tone="danger" onClick={() => deleteInvoice(r)} />}
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
          ].filter((c) => ["invoice_number", "invoice_date", "__actions"].includes(c.key) || !hiddenCols.has(c.key))}
          rows={invoices}
          footer={summary && {
            invoice_number: `${summary.count} invoice(s)`,
            taxable_amount: <span className="tabular">{formatMoney(summary.taxable_amount)}</span>,
            tax: <span className="tabular">{formatMoney(summary.tax_amount)}</span>,
            total_amount: <span className="tabular">{formatMoney(summary.total_amount)}</span>,
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
              <span>Page {page} of {totalPages} · {summary.count} total</span>
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

function InvoiceForm({ masters, onClose, onCreated }) {
  const [form, setForm] = useState({
    invoice_number: "", po_number: "", vendor_id: "", invoice_date: new Date().toISOString().slice(0, 10), due_date: "",
    project_id: "", category_id: "", sub_category_id: "", description: "",
    taxable_amount: "", cgst: "0", sgst: "0", igst: "0", other_tax: "0",
    pay_immediately: false, payment_date: new Date().toISOString().slice(0, 10),
    account_id: "", payment_mode: "NEFT", reference_number: "", remarks: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const total = ["taxable_amount", "cgst", "sgst", "igst", "other_tax"].reduce((s, k) => s + Number(form[k] || 0), 0);

  // Only offer vendors that can bill against the selected project - a
  // vendor with no project links at all is general/universal and always
  // shown. No project selected yet -> show every vendor the user can see
  // (already scoped server-side for ACCOUNTS - see project_scope_service).
  const availableVendors = form.project_id
    ? masters.vendors.filter((v) => !v.project_ids?.length || v.project_ids.includes(Number(form.project_id)))
    : masters.vendors;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/invoices", {
        ...form,
        vendor_id: Number(form.vendor_id),
        po_number: form.po_number || null,
        project_id: form.project_id || null,
        due_date: form.due_date || null,
        category_id: Number(form.category_id),
        sub_category_id: form.sub_category_id || null,
        taxable_amount: Number(form.taxable_amount),
        cgst: Number(form.cgst || 0), sgst: Number(form.sgst || 0), igst: Number(form.igst || 0), other_tax: Number(form.other_tax || 0),
        account_id: form.pay_immediately ? Number(form.account_id) : null,
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
      <h2 className="font-display font-semibold text-lg mb-4">New Supplier Invoice</h2>
      <form onSubmit={submit} className="space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <Select label="Project" value={form.project_id} onChange={(e) => { set("project_id", e.target.value); set("vendor_id", ""); }}>
            <option value="">— none —</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select label="Vendor" value={form.vendor_id} onChange={(e) => set("vendor_id", e.target.value)} required>
            <option value="">Select…</option>
            {availableVendors.map((v) => <option key={v.id} value={v.id}>{vendorLabel(v)}</option>)}
          </Select>
          <Input label="Invoice Number" value={form.invoice_number} onChange={(e) => set("invoice_number", e.target.value)} required />
          <Input label="Invoice Date" type="date" value={form.invoice_date} onChange={(e) => set("invoice_date", e.target.value)} required />
          <Input label="Due Date" type="date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} />
          <Select label="Expense Head" value={form.category_id} onChange={(e) => { set("category_id", e.target.value); set("sub_category_id", ""); }} required>
            <option value="">Select…</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <SubCategorySelect categoryId={form.category_id} value={form.sub_category_id} onChange={(v) => set("sub_category_id", v)} />
        </div>
        <Textarea label="PO Number(s)" value={form.po_number} onChange={(e) => set("po_number", e.target.value)} rows={2} placeholder="One or more PO numbers, e.g. one per line" />
        <Input label="Description" value={form.description} onChange={(e) => set("description", e.target.value)} />
        <div className="grid grid-cols-4 gap-4">
          <Input label="Taxable Amount" type="number" step="0.01" value={form.taxable_amount} onChange={(e) => set("taxable_amount", e.target.value)} required />
          <Input label="CGST" type="number" step="0.01" value={form.cgst} onChange={(e) => set("cgst", e.target.value)} />
          <Input label="SGST" type="number" step="0.01" value={form.sgst} onChange={(e) => set("sgst", e.target.value)} />
          <Input label="IGST" type="number" step="0.01" value={form.igst} onChange={(e) => set("igst", e.target.value)} />
        </div>
        <div className="text-sm text-ink/60">Total: <span className="tabular font-semibold text-ink">{formatMoney(total)}</span></div>

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
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : form.pay_immediately ? "Save & Pay" : "Save Invoice"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
