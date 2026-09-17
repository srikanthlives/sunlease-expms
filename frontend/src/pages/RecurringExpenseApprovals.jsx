import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { Card, Button, Input, StatusBadge, formatMoney, formatDate, vendorLabel } from "../components/ui";
import { CheckCircle2, XCircle, RefreshCw } from "lucide-react";

function emptyReview(row) {
  return {
    amount: row.amount ?? "",
    bill_number: row.bill_number ?? "",
    description: row.description ?? "",
    cgst: row.cgst || "",
    sgst: row.sgst || "",
    igst: row.igst || "",
    other_tax: row.other_tax || "",
  };
}

export default function RecurringExpenseApprovals() {
  const masters = useMasters();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [reviews, setReviews] = useState({});
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  function load() { client.get("/recurring-expenses/instances/pending").then((res) => setRows(res.data)); }
  useEffect(load, []);

  function reviewFor(row) { return reviews[row.id] || emptyReview(row); }
  function setField(row, field, value) {
    setReviews((s) => ({ ...s, [row.id]: { ...reviewFor(row), [field]: value } }));
  }

  async function submitAccountsReview(row) {
    setError("");
    try {
      const r = reviewFor(row);
      await client.post(`/recurring-expenses/instances/${row.id}/accounts-review`, {
        amount: r.amount !== "" ? Number(r.amount) : null,
        bill_number: r.bill_number || null,
        description: r.description || null,
        cgst: Number(r.cgst || 0),
        sgst: row.payee_type === "VENDOR" ? Number(r.sgst || 0) : 0,
        igst: row.payee_type === "VENDOR" ? Number(r.igst || 0) : 0,
        other_tax: Number(r.other_tax || 0),
      });
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function doReject(id) {
    setError("");
    try {
      await client.post(`/recurring-expenses/instances/${id}/reject`, { reason: rejectReason });
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const payeeName = (row) => {
    if (row.payee_type === "VENDOR") return vendorLabel(masters.vendors.find((v) => v.id === row.vendor_id)) || "—";
    return row.supplier_name || "—";
  };
  const projectName = (row) => masters.projects.find((p) => p.id === row.project_id)?.name || "—";
  const categoryName = (row) => masters.categories.find((c) => c.id === row.category_id)?.name || "—";
  const subCategoryName = (row) => masters.subCategories.find((s) => s.id === row.sub_category_id)?.name || null;

  if (masters.loading) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-semibold">Recurring Expense Approvals</h1>
          <p className="text-sm text-ink/50 mt-0.5">
            Bills generated ahead of their due date. Accounts confirms the actual amount and GST/tax breakdown — this
            posts it directly as an {"Invoice (Vendor Expense) or Direct Expense"}, no Admin approval needed.
          </p>
        </div>
        <Button variant="ghost" onClick={load}><RefreshCw size={14} /> Refresh</Button>
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {rows.length === 0 ? (
        <Card><div className="text-sm text-ink/40 py-6 text-center">Nothing pending confirmation right now.</div></Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row) => {
            const r = reviewFor(row);
            const isVendor = row.payee_type === "VENDOR";
            return (
              <Card key={row.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-sm font-semibold">{row.recurring_expense_name}</span>
                      <StatusBadge status={row.status} />
                      {row.amount_type === "OPEN" && <span className="text-[11px] text-ink/40 italic">Open Amount</span>}
                      <span className="text-[11px] text-ink/40 italic">{isVendor ? "Records as Invoice" : "Records as Direct Expense"}</span>
                    </div>
                    <div className="text-xs text-ink/50 mb-2">
                      Bill date {formatDate(row.occurrence_date)}{row.due_date ? ` · Due ${formatDate(row.due_date)}` : ""} · Project: {projectName(row)} · Payee: {payeeName(row)}
                      {" · Head: "}{categoryName(row)}{subCategoryName(row) ? ` / ${subCategoryName(row)}` : ""}
                    </div>
                    <div className="space-y-3 max-w-lg">
                      <div className="flex gap-3">
                        <Input label={row.amount_type === "OPEN" ? "Enter Bill Amount" : "Amount (correct if changed)"}
                          type="number" step="0.01"
                          value={r.amount}
                          onChange={(e) => setField(row, "amount", e.target.value)} />
                        <Input label={isVendor ? "Invoice Number" : "Voucher / Bill No"}
                          value={r.bill_number}
                          placeholder={isVendor ? "required to record as an Invoice" : "e.g. from the physical bill"}
                          onChange={(e) => setField(row, "bill_number", e.target.value)} />
                      </div>
                      {isVendor ? (
                        <div className="flex gap-3">
                          <Input label="CGST" type="number" step="0.01" value={r.cgst}
                            onChange={(e) => setField(row, "cgst", e.target.value)} />
                          <Input label="SGST" type="number" step="0.01" value={r.sgst}
                            onChange={(e) => setField(row, "sgst", e.target.value)} />
                          <Input label="IGST" type="number" step="0.01" value={r.igst}
                            onChange={(e) => setField(row, "igst", e.target.value)} />
                          <Input label="Other Tax" type="number" step="0.01" value={r.other_tax}
                            onChange={(e) => setField(row, "other_tax", e.target.value)} />
                        </div>
                      ) : (
                        <div className="flex gap-3">
                          <Input label="GST Amount" type="number" step="0.01" value={r.cgst}
                            onChange={(e) => setField(row, "cgst", e.target.value)} />
                          <Input label="Other Amount" type="number" step="0.01" value={r.other_tax}
                            onChange={(e) => setField(row, "other_tax", e.target.value)} />
                        </div>
                      )}
                      <Input label="Description"
                        value={r.description}
                        placeholder={`Description that will be recorded on the ${isVendor ? "Invoice" : "Expense"}`}
                        onChange={(e) => setField(row, "description", e.target.value)} />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 shrink-0">
                    <Button variant="accent" onClick={() => submitAccountsReview(row)}>
                      <CheckCircle2 size={14} /> Confirm
                    </Button>
                    <Button variant="danger" onClick={() => setRejectingId(row.id)}><XCircle size={14} /> Reject</Button>
                  </div>
                </div>
                {rejectingId === row.id && (
                  <div className="mt-4 pt-4 border-t border-ink/10 flex items-end gap-3">
                    <div className="flex-1">
                      <Input label="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} autoFocus />
                    </div>
                    <Button variant="danger" onClick={() => doReject(row.id)}>Confirm Reject</Button>
                    <Button variant="ghost" onClick={() => { setRejectingId(null); setRejectReason(""); }}>Cancel</Button>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
