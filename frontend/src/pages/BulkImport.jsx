import { useRef, useState } from "react";
import client, { apiErrorMessage, BASE_URL } from "../api/client";
import { Card, Button, Table, formatMoney } from "../components/ui";
import { UploadCloud, Download, CheckCircle2, XCircle } from "lucide-react";

function ResultTable({ rows }) {
  const columns = [
    { key: "row_number", header: "Row" },
    { key: "row_type", header: "Type" },
    {
      key: "status", header: "Status", render: (r) =>
        r.status === "OK"
          ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={14} /> OK</span>
          : <span className="inline-flex items-center gap-1 text-danger"><XCircle size={14} /> Error</span>,
    },
    { key: "expense_number", header: "Expense #", render: (r) => r.expense_number || "—" },
    { key: "invoice_number", header: "Invoice #", render: (r) => r.invoice_number || "—" },
    { key: "payment_number", header: "Payment #", render: (r) => r.payment_number || "—" },
    { key: "total_amount", header: "Amount", render: (r) => (r.total_amount ? formatMoney(r.total_amount) : "—") },
    {
      key: "errors", header: "Details", render: (r) =>
        r.errors?.length ? <span className="text-danger text-xs">{r.errors.join("; ")}</span> : "",
    },
  ];
  return <Table columns={columns} rows={rows} empty="No rows parsed." />;
}

export default function BulkImport() {
  const fileRef = useRef(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState(null);
  const [committed, setCommitted] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function pickFile() {
    setPreview(null);
    setCommitted(null);
    setError("");
    const f = fileRef.current.files[0];
    setFileName(f ? f.name : "");
  }

  async function runDryRun() {
    const f = fileRef.current.files[0];
    if (!f) { setError("Choose a file first"); return; }
    setBusy(true);
    setError("");
    setCommitted(null);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await client.post("/bulk-import/expenses?dry_run=true", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function runCommit() {
    const f = fileRef.current.files[0];
    if (!f) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await client.post("/bulk-import/expenses?dry_run=false", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCommitted(res.data);
      setPreview(null);
      fileRef.current.value = "";
      setFileName("");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const hasErrors = preview?.error_rows > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Bulk Import Expenses</h1>
        <p className="text-sm text-ink/50 mt-0.5">
          Upload an Excel sheet of invoices and direct expenses (optionally with payment details) to record
          them all in one go — each row becomes an Expense, plus a linked Invoice or Payment as appropriate,
          exactly as if entered by hand.
        </p>
      </div>

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold">1. Get the template</h2>
          <a
            href={`${BASE_URL}/api/v1/bulk-import/template`}
            onClick={(e) => {
              e.preventDefault();
              client.get("/bulk-import/template", { responseType: "blob" }).then((res) => {
                const url = URL.createObjectURL(res.data);
                const a = document.createElement("a");
                a.href = url;
                a.download = "expense_bulk_import_template.xlsx";
                a.click();
                URL.revokeObjectURL(url);
              });
            }}
          >
            <Button variant="secondary"><Download size={16} /> Download Template</Button>
          </a>
        </div>
        <p className="text-xs text-ink/50">
          Row Type is <strong>INVOICE</strong> (records an Invoice + its linked Expense — Vendor and Invoice
          Number required) or <strong>DIRECT</strong> (records a Direct Expense — Supplier Name/Bill Number
          optional). Project, Vendor, Category, Sub Category and Account are matched by their existing code or
          name — set up any missing Masters entries first. Set Pay Immediately to Y with Payment Date, Account
          and Payment Mode to also record the payment.
        </p>
      </Card>

      <Card className="space-y-4">
        <h2 className="font-display font-semibold">2. Upload &amp; preview</h2>
        <div className="flex items-center gap-3">
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" onChange={pickFile}
            className="text-sm file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-brand-700 file:text-white file:text-sm hover:file:bg-brand-800" />
          <Button onClick={runDryRun} disabled={busy || !fileName}>
            <UploadCloud size={16} /> {busy ? "Checking…" : "Preview"}
          </Button>
        </div>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      </Card>

      {preview && (
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold">
              Preview: {preview.ok_rows} of {preview.total_rows} rows valid
            </h2>
            <Button onClick={runCommit} disabled={busy || hasErrors}>
              {busy ? "Importing…" : "Confirm & Import"}
            </Button>
          </div>
          {hasErrors && (
            <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">
              Fix the errors below and re-upload — nothing is imported until every row is valid.
            </div>
          )}
          <ResultTable rows={preview.rows} />
        </Card>
      )}

      {committed && (
        <Card className="space-y-4">
          <h2 className="font-display font-semibold text-emerald-700">
            Imported {committed.ok_rows} row(s) successfully
          </h2>
          <ResultTable rows={committed.rows} />
        </Card>
      )}
    </div>
  );
}
