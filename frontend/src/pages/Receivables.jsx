import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, StatusBadge, StatCard, Button, IconButton, Input, Textarea, Select, formatMoney, formatDate } from "../components/ui";
import DateRangePicker, { defaultMonthRange } from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import { Plus, X, Trash2, Pencil, Send, CheckCircle2, XCircle, ArrowRightCircle } from "lucide-react";

const QUOTATION_STATUSES = ["DRAFT", "SENT", "ACCEPTED", "REJECTED", "CONVERTED"];
const PAYMENT_STATUSES = ["UNPAID", "PARTIALLY_PAID", "PAID"];
const PAYMENT_MODES = ["NEFT", "RTGS", "IMPS", "UPI", "CASH", "CHEQUE"];
const TABS = [
  { key: "quotations", label: "Quotations" },
  { key: "invoices", label: "Receivable Invoices" },
  { key: "payments", label: "Payments Received" },
];

// Shared read-only "label: value" row for detail modals below.
function DetailRow({ label, value }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-ink/40 font-medium">{label}</div>
      <div className="text-sm text-ink/80 mt-0.5">{value ?? "—"}</div>
    </div>
  );
}

function DetailModal({ title, statusBadge, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <div className="flex items-center gap-2 mb-5">
          <h2 className="font-display font-semibold text-lg">{title}</h2>
          {statusBadge}
        </div>
        <div className="space-y-5">{children}</div>
      </div>
    </div>
  );
}

function TaxFields({ form, set }) {
  const total = ["taxable_amount", "cgst", "sgst", "igst", "other_tax"].reduce((s, k) => s + Number(form[k] || 0), 0);
  return (
    <>
      <div className="grid grid-cols-4 gap-4">
        <Input label="Taxable Amount" type="number" step="0.01" value={form.taxable_amount} onChange={(e) => set("taxable_amount", e.target.value)} required />
        <Input label="CGST" type="number" step="0.01" value={form.cgst} onChange={(e) => set("cgst", e.target.value)} />
        <Input label="SGST" type="number" step="0.01" value={form.sgst} onChange={(e) => set("sgst", e.target.value)} />
        <Input label="IGST" type="number" step="0.01" value={form.igst} onChange={(e) => set("igst", e.target.value)} />
      </div>
      <div className="text-sm text-ink/60">Total: <span className="tabular font-semibold text-ink">{formatMoney(total)}</span></div>
    </>
  );
}

function QuotationDetailModal({ quotation, canManage, onClose }) {
  return (
    <DetailModal title={quotation.quotation_number} statusBadge={<StatusBadge status={quotation.status} />} onClose={onClose}>
      <div className="grid grid-cols-2 gap-4">
        <DetailRow label="Customer" value={quotation.customer_name} />
        <DetailRow label="Project" value={quotation.project_name} />
        <DetailRow label="Quotation Date" value={formatDate(quotation.quotation_date)} />
        <DetailRow label="Valid Until" value={quotation.valid_until ? formatDate(quotation.valid_until) : "—"} />
      </div>
      {quotation.description && <DetailRow label="Description" value={quotation.description} />}
      <div className="grid grid-cols-3 gap-4 bg-ink/5 rounded-md p-4">
        <DetailRow label="Taxable Amount" value={formatMoney(quotation.taxable_amount)} />
        <DetailRow label="Tax (CGST+SGST+IGST+Other)" value={formatMoney(Number(quotation.cgst) + Number(quotation.sgst) + Number(quotation.igst) + Number(quotation.other_tax))} />
        <DetailRow label="Total" value={<span className="font-semibold">{formatMoney(quotation.total_amount)}</span>} />
      </div>
      {quotation.status === "REJECTED" && quotation.rejection_reason && (
        <DetailRow label="Rejection Reason" value={quotation.rejection_reason} />
      )}
      {quotation.receivable_invoice_number && (
        <div className="text-xs text-ok bg-ok/10 rounded-md px-3 py-2 inline-block">
          Converted to invoice: <span className="font-semibold">{quotation.receivable_invoice_number}</span>
        </div>
      )}
      <div>
        <div className="text-[11px] uppercase tracking-wide text-ink/40 font-medium mb-1.5">Attachments</div>
        <Attachments documentType="QUOTATION" quotationId={quotation.id} readOnly={!canManage} label="Quotation / Proof" />
      </div>
    </DetailModal>
  );
}

function QuotationForm({ editing, onClose, onSaved }) {
  const masters = useMasters();
  const [form, setForm] = useState(editing ? {
    ...editing,
    project_id: editing.project_id || "",
    valid_until: editing.valid_until || "",
  } : {
    quotation_number: "", customer_name: "", project_id: "", quotation_date: new Date().toISOString().slice(0, 10), valid_until: "",
    description: "", taxable_amount: "", cgst: "0", sgst: "0", igst: "0", other_tax: "0",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        quotation_number: form.quotation_number, customer_name: form.customer_name, project_id: form.project_id || null, quotation_date: form.quotation_date,
        valid_until: form.valid_until || null, description: form.description || null,
        taxable_amount: Number(form.taxable_amount), cgst: Number(form.cgst || 0),
        sgst: Number(form.sgst || 0), igst: Number(form.igst || 0), other_tax: Number(form.other_tax || 0),
      };
      if (editing) await client.put(`/receivables/quotations/${editing.id}`, payload);
      else await client.post("/receivables/quotations", payload);
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
      <h2 className="font-display font-semibold text-lg mb-4">{editing ? `Edit ${editing.quotation_number}` : "New Quotation"}</h2>
      <form onSubmit={submit} className="space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Quotation Number" value={form.quotation_number} onChange={(e) => set("quotation_number", e.target.value)} required />
          <Input label="Customer Name" value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} required />
          <Select label="Project" value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
            <option value="">— none —</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Input label="Quotation Date" type="date" value={form.quotation_date} onChange={(e) => set("quotation_date", e.target.value)} required />
          <Input label="Valid Until" type="date" value={form.valid_until} onChange={(e) => set("valid_until", e.target.value)} />
        </div>
        <Input label="Description" value={form.description || ""} onChange={(e) => set("description", e.target.value)} />
        <TaxFields form={form} set={set} />
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save Quotation"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

function QuotationsTab({ canManage }) {
  const masters = useMasters();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState("");
  const [convertingId, setConvertingId] = useState(null);
  const [convertForm, setConvertForm] = useState({ invoice_number: "", invoice_date: new Date().toISOString().slice(0, 10), due_date: "" });
  const [viewing, setViewing] = useState(null);

  function load() {
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (projectId) params.project_id = projectId;
    client.get("/receivables/quotations", { params }).then((res) => setRows(res.data));
    client.get("/receivables/quotations/summary", { params }).then((res) => setSummary(res.data));
  }
  useEffect(load, [statusFilter, projectId]);

  async function send(id) { await client.post(`/receivables/quotations/${id}/send`); load(); }
  async function accept(id) { await client.post(`/receivables/quotations/${id}/accept`); load(); }
  async function reject(id) {
    const reason = window.prompt("Reason for rejection (optional):") || null;
    await client.post(`/receivables/quotations/${id}/reject`, { reason });
    load();
  }
  async function del(row) {
    if (!window.confirm(`Delete ${row.quotation_number}? This cannot be undone.`)) return;
    try {
      await client.delete(`/receivables/quotations/${row.id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }
  async function convert(e) {
    e.preventDefault();
    setError("");
    try {
      await client.post(`/receivables/quotations/${convertingId}/convert`, {
        invoice_number: convertForm.invoice_number, invoice_date: convertForm.invoice_date, due_date: convertForm.due_date || null,
      });
      setConvertingId(null);
      setConvertForm({ invoice_number: "", invoice_date: new Date().toISOString().slice(0, 10), due_date: "" });
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-end">
        <div className="flex items-end gap-4">
          <Select label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-48">
            <option value="">All Statuses</option>
            {QUOTATION_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-48">
            <option value="">All Projects</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </div>
        {canManage && <Button onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New Quotation</Button>}
      </div>

      {showForm && (
        <QuotationForm editing={editing} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} />
      )}

      {convertingId && (
        <Card className="relative max-w-md">
          <button onClick={() => setConvertingId(null)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h3 className="font-medium mb-3">Convert to Receivable Invoice</h3>
          <form onSubmit={convert} className="space-y-3">
            <Input label="Invoice Number" value={convertForm.invoice_number} onChange={(e) => setConvertForm((f) => ({ ...f, invoice_number: e.target.value }))} required />
            <Input label="Invoice Date" type="date" value={convertForm.invoice_date} onChange={(e) => setConvertForm((f) => ({ ...f, invoice_date: e.target.value }))} required />
            <Input label="Due Date" type="date" value={convertForm.due_date} onChange={(e) => setConvertForm((f) => ({ ...f, due_date: e.target.value }))} />
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
            <Button type="submit">Convert</Button>
          </form>
        </Card>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <StatCard label="Quotations" value={summary.count} />
          <StatCard label="Total Value" value={formatMoney(summary.total_amount)} />
        </div>
      )}

      <Card>
        <Table
          columns={[
            { key: "quotation_number", header: "Quotation #", render: (r) => <span className="whitespace-nowrap">{r.quotation_number}</span> },
            {
              key: "customer_name", header: "Customer",
              render: (r) => <span title={r.customer_name} className="block max-w-[200px] truncate">{r.customer_name}</span>,
            },
            {
              key: "project_name", header: "Project",
              render: (r) => { const text = r.project_name || "—"; return <span title={text} className="block max-w-[160px] truncate">{text}</span>; },
            },
            { key: "quotation_date", header: "Date", render: (r) => <span className="whitespace-nowrap">{formatDate(r.quotation_date)}</span> },
            { key: "valid_until", header: "Valid Until", render: (r) => <span className="whitespace-nowrap">{r.valid_until ? formatDate(r.valid_until) : "—"}</span> },
            { key: "total_amount", header: "Amount", render: (r) => <span className="tabular whitespace-nowrap">{formatMoney(r.total_amount)}</span> },
            { key: "status", header: "Status", render: (r) => <span className="whitespace-nowrap"><StatusBadge status={r.status} /></span> },
            { key: "receivable_invoice_number", header: "Invoice", render: (r) => <span className="whitespace-nowrap">{r.receivable_invoice_number || "—"}</span> },
            {
              key: "attachments", header: "Attachments",
              render: (r) => <Attachments documentType="QUOTATION" quotationId={r.id} compact label="Proof" readOnly={!canManage} />,
            },
            ...(canManage ? [{
              key: "__actions", header: "",
              render: (r) => (
                <div className="flex items-center gap-1 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                  {r.status !== "CONVERTED" && <IconButton bordered icon={Pencil} title="Edit" onClick={() => { setEditing(r); setShowForm(true); }} />}
                  {r.status === "DRAFT" && <IconButton bordered icon={Send} title="Send" onClick={() => send(r.id)} />}
                  {(r.status === "SENT" || r.status === "DRAFT") && <IconButton bordered icon={CheckCircle2} title="Accept" tone="ok" onClick={() => accept(r.id)} />}
                  {r.status !== "CONVERTED" && r.status !== "REJECTED" && <IconButton bordered icon={XCircle} title="Reject" tone="danger" onClick={() => reject(r.id)} />}
                  {r.status === "ACCEPTED" && <IconButton bordered icon={ArrowRightCircle} title="Convert to Invoice" tone="ok" onClick={() => { setConvertingId(r.id); setError(""); }} />}
                  {r.status === "DRAFT" && <IconButton bordered icon={Trash2} title="Delete" tone="danger" onClick={() => del(r)} />}
                </div>
              ),
            }] : []),
          ]}
          rows={rows}
          onRowClick={(r) => setViewing(r)}
          empty="No quotations yet."
        />
      </Card>

      {viewing && <QuotationDetailModal quotation={viewing} canManage={canManage} onClose={() => setViewing(null)} />}
    </div>
  );
}

function ReceivableInvoiceDetailModal({ invoice, canManage, onClose }) {
  const [payments, setPayments] = useState(null);

  useEffect(() => {
    client.get("/receivables/payments").then((res) => {
      setPayments(res.data.filter((p) => p.allocations.some((a) => a.receivable_invoice_id === invoice.id)));
    });
  }, [invoice.id]);

  return (
    <DetailModal title={invoice.invoice_number} statusBadge={<StatusBadge status={invoice.status} />} onClose={onClose}>
      <div className="grid grid-cols-2 gap-4">
        <DetailRow label="Customer" value={invoice.customer_name} />
        <DetailRow label="Project" value={invoice.project_name} />
        <DetailRow label="Invoice Date" value={formatDate(invoice.invoice_date)} />
        <DetailRow label="Due Date" value={invoice.due_date ? formatDate(invoice.due_date) : "—"} />
        {invoice.quotation_number && <DetailRow label="From Quotation" value={invoice.quotation_number} />}
        <DetailRow label="Payment Status" value={<StatusBadge status={invoice.payment_status} />} />
      </div>
      {invoice.po_number && <DetailRow label="PO Number(s)" value={<span className="whitespace-pre-wrap">{invoice.po_number}</span>} />}
      {invoice.description && <DetailRow label="Description" value={invoice.description} />}
      <div className="grid grid-cols-3 gap-4 bg-ink/5 rounded-md p-4">
        <DetailRow label="Taxable Amount" value={formatMoney(invoice.taxable_amount)} />
        <DetailRow label="Tax (CGST+SGST+IGST+Other)" value={formatMoney(Number(invoice.cgst) + Number(invoice.sgst) + Number(invoice.igst) + Number(invoice.other_tax))} />
        <DetailRow label="Total" value={<span className="font-semibold">{formatMoney(invoice.total_amount)}</span>} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <DetailRow label="Received" value={<span className="text-ok font-medium">{formatMoney(invoice.paid_amount)}</span>} />
        <DetailRow label="Balance Due" value={<span className="text-warn font-medium">{formatMoney(invoice.balance_due)}</span>} />
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide text-ink/40 font-medium mb-1.5">Payments Received Against This Invoice</div>
        {payments === null ? (
          <div className="text-sm text-ink/40">Loading…</div>
        ) : payments.length === 0 ? (
          <div className="text-sm text-ink/40">No payments recorded yet.</div>
        ) : (
          <div className="space-y-1.5">
            {payments.map((p) => {
              const alloc = p.allocations.find((a) => a.receivable_invoice_id === invoice.id);
              return (
                <div key={p.id} className="flex items-center justify-between bg-ink/5 rounded-md px-3 py-2 text-sm">
                  <span>{p.payment_number} · {formatDate(p.payment_date)} · {p.payment_mode}{p.is_cancelled && <span className="text-danger"> (Cancelled)</span>}</span>
                  <span className="tabular font-medium">{formatMoney(alloc?.allocated_amount)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide text-ink/40 font-medium mb-1.5">Attachments</div>
        <Attachments documentType="RECEIVABLE_INVOICE" receivableInvoiceId={invoice.id} readOnly={!canManage} label="Invoice / Proof" />
      </div>
    </DetailModal>
  );
}

function ReceivableInvoiceForm({ editing, onClose, onSaved }) {
  const masters = useMasters();
  const [form, setForm] = useState(editing ? {
    ...editing,
    project_id: editing.project_id || "",
    due_date: editing.due_date || "",
  } : {
    invoice_number: "", customer_name: "", project_id: "", invoice_date: new Date().toISOString().slice(0, 10), due_date: "",
    po_number: "", description: "", taxable_amount: "", cgst: "0", sgst: "0", igst: "0", other_tax: "0",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        invoice_number: form.invoice_number, customer_name: form.customer_name, project_id: form.project_id || null, invoice_date: form.invoice_date, due_date: form.due_date || null,
        po_number: form.po_number || null, description: form.description || null, taxable_amount: Number(form.taxable_amount),
        cgst: Number(form.cgst || 0), sgst: Number(form.sgst || 0), igst: Number(form.igst || 0), other_tax: Number(form.other_tax || 0),
      };
      if (editing) await client.put(`/receivables/invoices/${editing.id}`, payload);
      else await client.post("/receivables/invoices", payload);
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
      <h2 className="font-display font-semibold text-lg mb-4">{editing ? `Edit ${editing.invoice_number}` : "New Receivable Invoice"}</h2>
      <form onSubmit={submit} className="space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Invoice Number" value={form.invoice_number} onChange={(e) => set("invoice_number", e.target.value)} required />
          <Input label="Customer Name" value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} required />
          <Select label="Project" value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
            <option value="">— none —</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Input label="Invoice Date" type="date" value={form.invoice_date} onChange={(e) => set("invoice_date", e.target.value)} required />
          <Input label="Due Date" type="date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} />
        </div>
        <Textarea label="PO Number(s)" value={form.po_number || ""} onChange={(e) => set("po_number", e.target.value)} rows={2} placeholder="Customer's PO number(s), if any - e.g. one per line" />
        <Input label="Description" value={form.description} onChange={(e) => set("description", e.target.value)} />
        <TaxFields form={form} set={set} />
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save Invoice"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

function InvoicesTab({ canManage }) {
  const masters = useMasters();
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(defaultMonthRange);
  const [paymentStatus, setPaymentStatus] = useState("");
  const [projectId, setProjectId] = useState("");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => setBounds(res.data)).catch(() => {});
  }, []);

  function filterParams() {
    const params = {};
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    if (paymentStatus) params.payment_status = paymentStatus;
    if (projectId) params.project_id = projectId;
    return params;
  }
  function load() {
    client.get("/receivables/invoices", { params: filterParams() }).then((res) => setRows(res.data));
    client.get("/receivables/invoices/summary", { params: filterParams() }).then((res) => setSummary(res.data));
  }
  useEffect(load, [range.from, range.to, paymentStatus, projectId]);

  async function cancelInvoice(row) {
    const reason = window.prompt(`Cancel ${row.invoice_number}? Reason (optional):`);
    if (reason === null) return;
    try {
      await client.post(`/receivables/invoices/${row.id}/cancel`, { reason });
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }
  async function del(row) {
    if (!window.confirm(`Delete ${row.invoice_number}? This cannot be undone.`)) return;
    try {
      await client.delete(`/receivables/invoices/${row.id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      {showForm && (
        <ReceivableInvoiceForm editing={editing} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} />
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 mt-4 pt-4 border-t border-ink/10">
          <Select label="Payment Status" value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)} className="w-48">
            <option value="">All Payment Statuses</option>
            {PAYMENT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
          <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-48">
            <option value="">All Projects</option>
            {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          {canManage && <Button onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New Invoice</Button>}
        </div>
      </Card>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Invoices" value={summary.count} />
          <StatCard label="Total Billed" value={formatMoney(summary.total_amount)} />
          <StatCard label="Received" value={formatMoney(summary.paid_amount)} tone="ok" />
          <StatCard label="Outstanding" value={formatMoney(summary.balance_due)} tone="warn" />
        </div>
      )}

      <Card>
        <Table
          columns={[
            { key: "invoice_number", header: "Invoice #", render: (r) => <span className="whitespace-nowrap">{r.invoice_number}</span> },
            {
              key: "customer_name", header: "Customer",
              render: (r) => <span title={r.customer_name} className="block max-w-[200px] truncate">{r.customer_name}</span>,
            },
            {
              key: "project_name", header: "Project",
              render: (r) => { const text = r.project_name || "—"; return <span title={text} className="block max-w-[160px] truncate">{text}</span>; },
            },
            {
              key: "quotation_number", header: "Quotation",
              render: (r) => r.quotation_number ? <span className="text-xs text-ink/60 whitespace-nowrap">{r.quotation_number}</span> : "—",
            },
            {
              key: "po_number", header: "PO Number",
              render: (r) => { const text = r.po_number || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            { key: "invoice_date", header: "Date", render: (r) => <span className="whitespace-nowrap">{formatDate(r.invoice_date)}</span> },
            { key: "due_date", header: "Due Date", render: (r) => <span className="whitespace-nowrap">{r.due_date ? formatDate(r.due_date) : "—"}</span> },
            { key: "total_amount", header: "Amount", render: (r) => <span className="tabular whitespace-nowrap">{formatMoney(r.total_amount)}</span> },
            { key: "paid_amount", header: "Received", render: (r) => <span className="tabular whitespace-nowrap">{formatMoney(r.paid_amount)}</span> },
            { key: "balance_due", header: "Balance", render: (r) => <span className="tabular font-medium whitespace-nowrap">{formatMoney(r.balance_due)}</span> },
            { key: "payment_status", header: "Payment", render: (r) => <span className="whitespace-nowrap"><StatusBadge status={r.payment_status} /></span> },
            { key: "status", header: "Status", render: (r) => <span className="whitespace-nowrap"><StatusBadge status={r.status} /></span> },
            {
              key: "attachments", header: "Attachments",
              render: (r) => <Attachments documentType="RECEIVABLE_INVOICE" receivableInvoiceId={r.id} compact label="Proof" readOnly={!canManage} />,
            },
            ...(canManage ? [{
              key: "__actions", header: "",
              render: (r) => r.status === "ACTIVE" && (
                <div className="flex items-center gap-1 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                  <IconButton bordered icon={Pencil} title="Edit" onClick={() => { setEditing(r); setShowForm(true); }} />
                  {Number(r.paid_amount) === 0 && !r.quotation_id && <IconButton bordered icon={Trash2} title="Delete" tone="danger" onClick={() => del(r)} />}
                  {Number(r.paid_amount) === 0 && <IconButton bordered icon={XCircle} title="Cancel" tone="danger" onClick={() => cancelInvoice(r)} />}
                </div>
              ),
            }] : []),
          ]}
          rows={rows}
          onRowClick={(r) => setViewing(r)}
          empty="No receivable invoices for this filter."
        />
      </Card>

      {viewing && <ReceivableInvoiceDetailModal invoice={viewing} canManage={canManage} onClose={() => setViewing(null)} />}
    </div>
  );
}

function ReceivablePaymentDetailModal({ payment, masters, onClose }) {
  return (
    <DetailModal
      title={payment.payment_number}
      statusBadge={payment.is_cancelled ? <StatusBadge status="CANCELLED" /> : <StatusBadge status="ACTIVE" />}
      onClose={onClose}
    >
      <div className="grid grid-cols-2 gap-4">
        <DetailRow label="Payment Date" value={formatDate(payment.payment_date)} />
        <DetailRow label="Account" value={masters.accounts.find((a) => a.id === payment.account_id)?.account_name || "—"} />
        <DetailRow label="Payment Mode" value={payment.payment_mode} />
        <DetailRow label="Reference / UTR" value={payment.reference_number} />
      </div>
      {payment.remarks && <DetailRow label="Remarks" value={payment.remarks} />}
      <div>
        <div className="text-[11px] uppercase tracking-wide text-ink/40 font-medium mb-1.5">Allocated To</div>
        <div className="space-y-1.5">
          {payment.allocations.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-ink/5 rounded-md px-3 py-2 text-sm">
              <span>{a.invoice_number || `#${a.receivable_invoice_id}`}</span>
              <span className="tabular font-medium">{formatMoney(a.allocated_amount)}</span>
            </div>
          ))}
        </div>
        <div className="text-sm text-right text-ink/60 mt-2">Total: <span className="tabular font-semibold text-ink">{formatMoney(payment.amount)}</span></div>
      </div>
    </DetailModal>
  );
}

function ReceivablePaymentForm({ onClose, onCreated }) {
  const masters = useMasters();
  const [form, setForm] = useState({
    payment_date: new Date().toISOString().slice(0, 10), account_id: "", payment_mode: "NEFT",
    reference_number: "", remarks: "",
  });
  const [customerFilter, setCustomerFilter] = useState("");
  const [outstanding, setOutstanding] = useState([]);
  const [allocations, setAllocations] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    client.get("/receivables/invoices", { params: { status: "ACTIVE", page_size: 500 } }).then((res) => {
      setOutstanding(res.data.filter((inv) => inv.payment_status !== "PAID"));
    });
  }, []);

  const filtered = customerFilter
    ? outstanding.filter((inv) => inv.customer_name.toLowerCase().includes(customerFilter.toLowerCase()))
    : outstanding;

  function addAllocation(invoiceId) {
    if (allocations.find((a) => a.receivable_invoice_id === invoiceId)) return;
    const inv = outstanding.find((i) => i.id === invoiceId);
    setAllocations((a) => [...a, { receivable_invoice_id: invoiceId, allocated_amount: inv ? String(inv.balance_due) : "" }]);
  }
  function updateAllocation(invoiceId, amount) {
    setAllocations((a) => a.map((x) => (x.receivable_invoice_id === invoiceId ? { ...x, allocated_amount: amount } : x)));
  }
  function removeAllocation(invoiceId) {
    setAllocations((a) => a.filter((x) => x.receivable_invoice_id !== invoiceId));
  }

  const total = allocations.reduce((s, a) => s + Number(a.allocated_amount || 0), 0);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/receivables/payments", {
        ...form,
        account_id: Number(form.account_id),
        allocations: allocations.map((a) => ({ receivable_invoice_id: a.receivable_invoice_id, allocated_amount: Number(a.allocated_amount) })),
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
      <h2 className="font-display font-semibold text-lg mb-4">Record Payment Received</h2>
      <form onSubmit={submit} className="space-y-4 max-w-3xl">
        <div className="grid grid-cols-3 gap-4">
          <Input label="Payment Date" type="date" value={form.payment_date} onChange={(e) => set("payment_date", e.target.value)} required />
          <Select label="Account" value={form.account_id} onChange={(e) => set("account_id", e.target.value)} required>
            <option value="">Select…</option>
            {masters.accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>)}
          </Select>
          <Select label="Payment Mode" value={form.payment_mode} onChange={(e) => set("payment_mode", e.target.value)}>
            {PAYMENT_MODES.map((m) => <option key={m}>{m}</option>)}
          </Select>
          <Input label="Reference / UTR" value={form.reference_number} onChange={(e) => set("reference_number", e.target.value)} />
          <Input label="Filter by Customer" value={customerFilter} onChange={(e) => setCustomerFilter(e.target.value)} />
        </div>

        {filtered.length > 0 ? (
          <div>
            <div className="text-xs font-medium text-ink/60 mb-2">Outstanding Invoices — click to allocate</div>
            <div className="flex flex-wrap gap-2">
              {filtered.map((inv) => (
                <button type="button" key={inv.id} onClick={() => addAllocation(inv.id)}
                  className="text-xs border border-ink/15 rounded-md px-2.5 py-1.5 hover:bg-brand-50 disabled:opacity-30"
                  disabled={!!allocations.find((a) => a.receivable_invoice_id === inv.id)}>
                  {inv.invoice_number}
                  <span className="text-ink/50"> · {inv.customer_name}</span>
                  {" · Balance "}{formatMoney(inv.balance_due)}
                  {" "}<span className="text-ink/40">({inv.payment_status})</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-xs text-ink/40">No unpaid receivable invoices found.</div>
        )}

        {allocations.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-ink/60">Allocations</div>
            {allocations.map((a) => {
              const inv = outstanding.find((i) => i.id === a.receivable_invoice_id);
              const balance = Number(inv?.balance_due ?? 0);
              const entered = Number(a.allocated_amount || 0);
              const overAllocated = entered > balance;
              return (
                <div key={a.receivable_invoice_id} className="bg-brand-50 rounded-md px-3 py-2">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{inv?.invoice_number} — {inv?.customer_name}</div>
                      <div className="text-[11px] text-ink/50">Balance remaining: <span className="tabular font-medium text-ink/70">{formatMoney(balance)}</span></div>
                    </div>
                    <input
                      type="number" step="0.01" placeholder="Amount" value={a.allocated_amount}
                      max={balance} min="0"
                      onChange={(e) => updateAllocation(a.receivable_invoice_id, e.target.value)}
                      className={`w-32 rounded border px-2 py-1 text-sm tabular ${overAllocated ? "border-danger text-danger" : "border-ink/15"}`}
                    />
                    <button type="button" onClick={() => removeAllocation(a.receivable_invoice_id)} className="text-ink/30 hover:text-danger"><Trash2 size={15} /></button>
                  </div>
                  {overAllocated && <div className="text-[11px] text-danger mt-1">Exceeds the outstanding balance of {formatMoney(balance)}</div>}
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

function ReceivablePaymentEditForm({ editing, onClose, onSaved }) {
  const masters = useMasters();
  const [form, setForm] = useState({
    payment_date: editing.payment_date, account_id: editing.account_id,
    payment_mode: editing.payment_mode, reference_number: editing.reference_number || "", remarks: editing.remarks || "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.put(`/receivables/payments/${editing.id}`, {
        payment_date: form.payment_date, account_id: Number(form.account_id), payment_mode: form.payment_mode,
        reference_number: form.reference_number || null, remarks: form.remarks || null,
      });
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
      <h2 className="font-display font-semibold text-lg mb-4">Edit {editing.payment_number}</h2>
      <p className="text-xs text-ink/50 -mt-2 mb-4">Amount and allocations can't be changed here - delete and re-record the payment instead if those are wrong.</p>
      <form onSubmit={submit} className="space-y-4 max-w-xl">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Payment Date" type="date" value={form.payment_date} onChange={(e) => set("payment_date", e.target.value)} required />
          <Select label="Account" value={form.account_id} onChange={(e) => set("account_id", e.target.value)} required>
            {masters.accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>)}
          </Select>
          <Select label="Payment Mode" value={form.payment_mode} onChange={(e) => set("payment_mode", e.target.value)}>
            {PAYMENT_MODES.map((m) => <option key={m}>{m}</option>)}
          </Select>
          <Input label="Reference / UTR" value={form.reference_number} onChange={(e) => set("reference_number", e.target.value)} />
        </div>
        <Input label="Remarks" value={form.remarks} onChange={(e) => set("remarks", e.target.value)} />
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save Changes"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

function PaymentsTab({ canManage }) {
  const masters = useMasters();
  const [rows, setRows] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);

  function load() { client.get("/receivables/payments").then((res) => setRows(res.data)); }
  useEffect(load, []);

  async function del(row) {
    if (!window.confirm(`Delete ${row.payment_number}? The invoice(s) it was allocated to will fall back to unpaid / partially paid. This cannot be undone.`)) return;
    try {
      await client.delete(`/receivables/payments/${row.id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        {canManage && <Button onClick={() => setShowForm(true)}><Plus size={16} /> Record Payment</Button>}
      </div>
      {showForm && <ReceivablePaymentForm onClose={() => setShowForm(false)} onCreated={() => { setShowForm(false); load(); }} />}
      {editing && (
        <ReceivablePaymentEditForm editing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
      <Card>
        <Table
          columns={[
            { key: "payment_number", header: "Payment #", render: (r) => <span className="whitespace-nowrap">{r.payment_number}</span> },
            { key: "payment_date", header: "Date", render: (r) => <span className="whitespace-nowrap">{formatDate(r.payment_date)}</span> },
            {
              key: "account_id", header: "Account",
              render: (r) => { const text = masters.accounts.find((a) => a.id === r.account_id)?.account_name || "—"; return <span title={text} className="block max-w-[160px] truncate">{text}</span>; },
            },
            { key: "payment_mode", header: "Mode", render: (r) => <span className="whitespace-nowrap">{r.payment_mode}</span> },
            {
              key: "reference_number", header: "Reference",
              render: (r) => { const text = r.reference_number || "—"; return <span title={text} className="block max-w-[140px] truncate">{text}</span>; },
            },
            { key: "amount", header: "Amount", render: (r) => <span className="tabular whitespace-nowrap">{formatMoney(r.amount)}</span> },
            {
              key: "allocations", header: "Allocated To",
              render: (r) => { const text = r.allocations.map((a) => a.invoice_number || `#${a.receivable_invoice_id}`).join(", "); return <span title={text} className="block max-w-[220px] truncate">{text}</span>; },
            },
            {
              key: "is_cancelled", header: "Status",
              render: (r) => <span className="whitespace-nowrap">{r.is_cancelled ? <span className="text-danger text-xs font-medium">CANCELLED</span> : <span className="text-ok text-xs font-medium">ACTIVE</span>}</span>,
            },
            ...(canManage ? [{
              key: "__actions", header: "",
              render: (r) => !r.is_cancelled && (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <IconButton bordered icon={Pencil} title="Edit" onClick={() => setEditing(r)} />
                  <IconButton bordered icon={Trash2} title="Delete" tone="danger" onClick={() => del(r)} />
                </div>
              ),
            }] : []),
          ]}
          rows={rows}
          onRowClick={(r) => setViewing(r)}
          empty="No payments received yet."
        />
      </Card>

      {viewing && <ReceivablePaymentDetailModal payment={viewing} masters={masters} onClose={() => setViewing(null)} />}
    </div>
  );
}

export default function Receivables() {
  const { user } = useAuth();
  const [tab, setTab] = useState("quotations");
  const canManage = ["ADMIN", "SUPER_ADMIN", "SUPER_ACCOUNTS"].includes(user?.role);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Receivables</h1>
        <p className="text-sm text-ink/50 mt-0.5">Quotations and invoices issued to customers, tracked through to payment.</p>
      </div>

      <div className="flex gap-1 border-b border-ink/10">
        {TABS.map((t) => (
          <button
            key={t.key} type="button" onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key ? "border-brand-600 text-brand-700" : "border-transparent text-ink/50 hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "quotations" && <QuotationsTab canManage={canManage} />}
      {tab === "invoices" && <InvoicesTab canManage={canManage} />}
      {tab === "payments" && <PaymentsTab canManage={canManage} />}
    </div>
  );
}
