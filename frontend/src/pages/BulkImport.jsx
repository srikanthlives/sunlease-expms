import { useRef, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Table, TruncatedText, formatMoney } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { UploadCloud, Download, FileDown, CheckCircle2, XCircle } from "lucide-react";

const STATUS_COLUMN = {
  key: "status", header: "Status", render: (r) =>
    r.status === "OK"
      ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={14} /> OK</span>
      : <span className="inline-flex items-center gap-1 text-danger"><XCircle size={14} /> Error</span>,
};

const ERROR_COLUMN = {
  key: "errors", header: "Details",
  render: (r) => r.errors?.length
    ? <TruncatedText text={r.errors.join("; ")} width={320} className="text-danger text-xs" empty="" />
    : "",
};

const AMOUNT_COLUMN = {
  key: "total_amount", header: "Amount", align: "right",
  render: (r) => (r.total_amount ? formatMoney(r.total_amount) : "—"),
};

/** The two imports share one flow - download template, upload, dry-run
 * preview, confirm - and differ only in endpoints, result columns and
 * help text. */
const IMPORTS = {
  expenses: {
    title: "Expenses",
    heading: "Bulk Import / Export — Expenses",
    blurb: "Upload an Excel sheet of invoices and direct expenses (optionally with payment details) to record them all in one go — each row becomes an Expense, plus a linked Invoice or Payment as appropriate, exactly as if entered by hand.",
    templatePath: "/bulk-import/template",
    templateFile: "expense_bulk_import_template.xlsx",
    importPath: "/bulk-import/expenses",
    exportPath: "/bulk-import/export",
    exportFile: "expense_export.xlsx",
    exportNote: "Invoice and direct expenses only — claim-sourced and recurring-sourced expenses are created by their own workflow and are not exported. An expense paid by more than one payment exports with its payment columns blank, since a single row can't express that.",
    help: (
      <>
        Row Type is <strong>INVOICE</strong> (records an Invoice + its linked Expense — Vendor and Invoice
        Number required) or <strong>DIRECT</strong> (records an Expense — Supplier Name/Bill Number
        optional). Project, Vendor, Category, Sub Category and Account are matched by their existing code or
        name — set up any missing Masters entries first. Set Pay Immediately to Y with Payment Date, Account
        and Payment Mode to also record the payment.
      </>
    ),
    columns: [
      { key: "row_number", header: "Row" },
      { key: "row_type", header: "Type" },
      STATUS_COLUMN,
      { key: "expense_number", header: "Expense #", render: (r) => r.expense_number || "—" },
      { key: "invoice_number", header: "Invoice #", render: (r) => r.invoice_number || "—" },
      { key: "payment_number", header: "Payment #", render: (r) => r.payment_number || "—" },
      AMOUNT_COLUMN,
      ERROR_COLUMN,
    ],
  },
  funds: {
    title: "Transfers & Funding",
    heading: "Bulk Import / Export — Transfers & Funding",
    blurb: "Upload an Excel sheet of funding received, repayments made and transfers between your own accounts. Each row becomes a Fund Transfer entry, validated exactly as if entered by hand on the Funds page.",
    templatePath: "/bulk-import/funds-template",
    templateFile: "fund_transfers_import_template.xlsx",
    importPath: "/bulk-import/fund-transfers",
    exportPath: "/bulk-import/funds-export",
    exportFile: "fund_transfers_export.xlsx",
    exportNote: "Funding, repayments and transfers in the template's own layout, with the transfer number, verified and cancelled state added as extra read-only columns.",
    roles: ["ADMIN", "SUPER_ADMIN"],
    help: (
      <>
        Kind is <strong>FUNDING</strong> (money in from a funding entity — To Account required, no From
        Account), <strong>REPAYMENT</strong> (money back out to that entity — From Account required, no To
        Account) or <strong>TRANSFER</strong> (between two of your own accounts — both required). Accounts
        and Funding Entity are matched by name, so set up any missing ones first. Funding Type
        (LOAN / CAPITAL / ADVANCE / OTHER) applies to FUNDING and REPAYMENT rows and defaults to LOAN.
        Imported entries start <strong>unverified</strong>.
      </>
    ),
    columns: [
      { key: "row_number", header: "Row" },
      { key: "row_type", header: "Kind" },
      STATUS_COLUMN,
      { key: "transfer_number", header: "Transfer #", render: (r) => r.transfer_number || "—" },
      AMOUNT_COLUMN,
      ERROR_COLUMN,
    ],
  },
};

function ImportPanel({ config }) {
  const fileRef = useRef(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState(null);
  const [committed, setCommitted] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [includeCancelled, setIncludeCancelled] = useState(false);

  function pickFile() {
    setPreview(null);
    setCommitted(null);
    setError("");
    const f = fileRef.current.files[0];
    setFileName(f ? f.name : "");
  }

  async function send(dryRun) {
    const f = fileRef.current.files[0];
    if (!f) { setError("Choose a file first"); return; }
    setBusy(true);
    setError("");
    if (dryRun) setCommitted(null);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await client.post(`${config.importPath}?dry_run=${dryRun}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (dryRun) {
        setPreview(res.data);
      } else {
        setCommitted(res.data);
        setPreview(null);
        fileRef.current.value = "";
        setFileName("");
      }
    } catch (err) {
      setError(apiErrorMessage(err));
      if (dryRun) setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  function download(path, filename, params) {
    setError("");
    client.get(path, { responseType: "blob", params }).then((res) => {
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }).catch((err) => setError(apiErrorMessage(err)));
  }

  function exportRows() {
    download(config.exportPath, config.exportFile, {
      date_from: from || undefined,
      date_to: to || undefined,
      include_cancelled: includeCancelled || undefined,
    });
  }

  const hasErrors = preview?.error_rows > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">{config.heading}</h1>
        <p className="text-sm text-ink/50 mt-0.5">{config.blurb}</p>
      </div>

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold">1. Get the template</h2>
          <Button variant="outline" onClick={() => download(config.templatePath, config.templateFile)}>
            <Download size={16} /> Download Template
          </Button>
        </div>
        <p className="text-xs text-ink/50">{config.help}</p>
      </Card>

      <Card className="space-y-4">
        <h2 className="font-display font-semibold">2. Upload &amp; preview</h2>
        <div className="flex items-center gap-3">
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" onChange={pickFile}
            className="text-sm file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-brand-700 file:text-white file:text-sm hover:file:bg-brand-800" />
          <Button onClick={() => send(true)} disabled={busy || !fileName}>
            <UploadCloud size={16} /> {busy ? "Checking…" : "Preview"}
          </Button>
        </div>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      </Card>

      <Card className="space-y-4">
        <div>
          <h2 className="font-display font-semibold">Export existing records</h2>
          <p className="text-xs text-ink/50 mt-0.5">
            Downloads what is already recorded, using the same columns as the template above — so an export
            can be edited and uploaded back. {config.exportNote}{" "}
            <strong>Re-uploading an export creates new records, it does not update the existing ones</strong>,
            so remove any row you do not want duplicated.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-44"><Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
          <div className="w-44"><Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
          <label className="flex items-center gap-2 text-sm pb-2">
            <input type="checkbox" checked={includeCancelled} onChange={(e) => setIncludeCancelled(e.target.checked)} />
            Include cancelled
          </label>
          <Button variant="outline" className="mb-0.5" onClick={exportRows}><FileDown size={16} /> Export to Excel</Button>
        </div>
      </Card>

      {preview && (
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold">
              Preview: {preview.ok_rows} of {preview.total_rows} rows valid
            </h2>
            <Button onClick={() => send(false)} disabled={busy || hasErrors}>
              {busy ? "Importing…" : "Confirm & Import"}
            </Button>
          </div>
          {hasErrors && (
            <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">
              Fix the errors below and re-upload — nothing is imported until every row is valid.
            </div>
          )}
          <Table columns={config.columns} rows={preview.rows} oneLine empty="No rows parsed." />
        </Card>
      )}

      {committed && (
        <Card className="space-y-4">
          <h2 className="font-display font-semibold text-emerald-700">
            Imported {committed.ok_rows} row(s) successfully
          </h2>
          <Table columns={config.columns} rows={committed.rows} oneLine empty="No rows parsed." />
        </Card>
      )}
    </div>
  );
}

export default function BulkImport() {
  const { user } = useAuth();
  const tabs = Object.entries(IMPORTS).filter(([, c]) => !c.roles || c.roles.includes(user?.role));
  const [tab, setTab] = useState(tabs[0]?.[0] || "expenses");
  const config = IMPORTS[tab];

  return (
    <div className="space-y-5">
      {tabs.length > 1 && (
        <div className="flex gap-1 border-b border-ink/10">
          {tabs.map(([key, c]) => (
            <button key={key} onClick={() => setTab(key)}
              className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === key ? "border-brand-500 text-ink" : "border-transparent text-ink/50 hover:text-ink"}`}>
              {c.title}
            </button>
          ))}
        </div>
      )}
      {config && <ImportPanel key={tab} config={config} />}
    </div>
  );
}
