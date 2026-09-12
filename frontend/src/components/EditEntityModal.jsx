import { useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useMasters } from "../hooks/useMasters";
import { Card, Button, Input, Select, vendorLabel } from "./ui";
import { X, CheckCircle2 } from "lucide-react";

const FIELD_SETS = {
  EXPENSE: (masters) => [
    { key: "expense_date", label: "Date", type: "date" },
    { key: "description", label: "Description", type: "text" },
    { key: "project_id", label: "Project", type: "select", options: masters.projects, optionLabel: "name" },
    { key: "supplier_name", label: "Supplier Name", type: "text" },
    { key: "bill_number", label: "Voucher / Bill No", type: "text" },
    { key: "category_id", label: "Category", type: "select", options: masters.categories, optionLabel: "name" },
    { key: "sub_category_id", label: "Sub-Category", type: "select", options: masters.subCategories, optionLabel: "name", dependsOn: "category_id" },
    { key: "base_amount", label: "Base Amount", type: "number" },
    { key: "gst_amount", label: "GST Amount", type: "number" },
    { key: "other_amount", label: "Other Amount", type: "number", hint: "Any amount beyond Base + GST (rounding, misc. charges, etc.) - included in Total." },
  ],
  INVOICE: (masters) => [
    { key: "invoice_number", label: "Invoice Number", type: "text" },
    { key: "vendor_id", label: "Vendor", type: "select", options: masters.vendors, optionLabel: vendorLabel },
    { key: "invoice_date", label: "Invoice Date", type: "date" },
    { key: "due_date", label: "Due Date", type: "date" },
    { key: "project_id", label: "Project", type: "select", options: masters.projects, optionLabel: "name" },
    { key: "category_id", label: "Category", type: "select", options: masters.categories, optionLabel: "name" },
    { key: "sub_category_id", label: "Sub-Category", type: "select", options: masters.subCategories, optionLabel: "name", dependsOn: "category_id" },
    { key: "description", label: "Description", type: "text" },
    { key: "taxable_amount", label: "Taxable Amount", type: "number" },
    { key: "cgst", label: "CGST", type: "number" },
    { key: "sgst", label: "SGST", type: "number" },
    { key: "igst", label: "IGST", type: "number" },
    { key: "other_tax", label: "Other Tax", type: "number" },
  ],
  PAYMENT: (masters) => [
    { key: "payment_date", label: "Payment Date", type: "date" },
    { key: "account_id", label: "Account", type: "select", options: masters.accounts, optionLabel: "account_name" },
    { key: "payment_mode", label: "Payment Mode", type: "select", options: [{ id: "NEFT" }, { id: "RTGS" }, { id: "IMPS" }, { id: "UPI" }, { id: "CASH" }, { id: "CHEQUE" }], optionLabel: "id", staticOptions: true },
    { key: "reference_number", label: "Reference / UTR", type: "text" },
    { key: "remarks", label: "Remarks", type: "text" },
  ],
};

// Fields that sum to an entity's Total, used to show a live "New Total"
// preview as the user edits amount fields - the actual computation always
// happens server-side (see edit_request_service.apply_changes), this is
// purely so the effect of changing e.g. Other Amount is visible before
// saving, instead of a surprise once the list reloads.
const AMOUNT_PARTS = {
  EXPENSE: [{ key: "base_amount", label: "Base" }, { key: "gst_amount", label: "GST" }, { key: "other_amount", label: "Other" }],
  INVOICE: [
    { key: "taxable_amount", label: "Taxable" }, { key: "cgst", label: "CGST" }, { key: "sgst", label: "SGST" },
    { key: "igst", label: "IGST" }, { key: "other_tax", label: "Other Tax" },
  ],
};

const ENDPOINTS = { EXPENSE: "/expenses", INVOICE: "/invoices", PAYMENT: "/payments" };
const LABELS = { EXPENSE: "Expense", INVOICE: "Invoice", PAYMENT: "Payment" };

export default function EditEntityModal({ entityType, entity, onClose, onSaved }) {
  const { user } = useAuth();
  const masters = useMasters();
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  // Accounts edits directly and in full while the record is unverified;
  // once Admin/Super Admin verifies it, Accounts drops to the
  // edit-request/approval path (Admin always edits directly, regardless).
  const isDirect = isAdmin || !entity.is_verified;
  const fields = FIELD_SETS[entityType](masters);

  const [form, setForm] = useState(Object.fromEntries(fields.map((f) => [f.key, entity[f.key] ?? ""])));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [submittedForApproval, setSubmittedForApproval] = useState(false);

  function set(k, v) { setForm((s) => ({ ...s, [k]: v })); }

  const amountParts = AMOUNT_PARTS[entityType];
  const newTotal = amountParts ? amountParts.reduce((sum, f) => sum + (Number(form[f.key]) || 0), 0) : null;

  function buildChanges() {
    // Only send fields that actually differ from the original value, so
    // Accounts' edit requests capture a clean diff and Admin's direct edits
    // don't touch untouched fields.
    const changes = {};
    for (const f of fields) {
      const original = entity[f.key] ?? "";
      const current = form[f.key] ?? "";
      if (String(original) !== String(current)) {
        changes[f.key] = current === "" ? null : current;
      }
    }
    return changes;
  }

  async function submit(e) {
    e.preventDefault();
    const changes = buildChanges();
    if (Object.keys(changes).length === 0) {
      setError("No fields were changed.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (isDirect) {
        await client.put(`${ENDPOINTS[entityType]}/${entity.id}`, changes);
        onSaved();
      } else {
        await client.post("/edit-requests", { entity_type: entityType, entity_id: entity.id, changes });
        setSubmittedForApproval(true);
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (submittedForApproval) {
    return (
      <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
        <Card className="max-w-sm relative" onClick={(e) => e.stopPropagation()}>
          <div className="text-center py-2">
            <CheckCircle2 className="mx-auto text-ok mb-3" size={32} />
            <h3 className="font-display font-semibold text-lg mb-1">Submitted for Approval</h3>
            <p className="text-sm text-ink/50 mb-4">Your proposed changes to this {LABELS[entityType].toLowerCase()} are pending Admin review. Nothing has changed yet.</p>
            <Button onClick={() => { onClose(); onSaved(); }}>Done</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <Card className="max-w-2xl w-full relative max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <h2 className="font-display font-semibold text-lg mb-1">Edit {LABELS[entityType]}</h2>
        <p className="text-xs text-ink/50 mb-4">
          {isDirect
            ? "Changes apply immediately."
            : entity.is_verified
            ? "This record has been verified by Admin and is locked - your changes will be submitted for approval before they take effect."
            : "Your changes will be submitted to an Admin for approval before they take effect."}
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {fields.map((f) => (
              <div key={f.key}>
                {f.type === "select" ? (
                  <Select label={f.label} value={form[f.key] || ""} onChange={(e) => set(f.key, e.target.value)} disabled={f.dependsOn && !form[f.dependsOn]}>
                    <option value="">— none —</option>
                    {(f.dependsOn ? f.options.filter((o) => String(o.category_id) === String(form[f.dependsOn])) : f.options).map((o) => (
                      <option key={o.id} value={o.id}>
                        {f.staticOptions ? o.id : (typeof f.optionLabel === "function" ? f.optionLabel(o) : o[f.optionLabel])}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    label={f.label} type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                    step={f.type === "number" ? "0.01" : undefined}
                    value={form[f.key] || ""} onChange={(e) => set(f.key, e.target.value)}
                  />
                )}
                {f.hint && <p className="text-[11px] text-ink/40 mt-1">{f.hint}</p>}
              </div>
            ))}
          </div>
          {newTotal != null && (
            <div className="text-sm text-ink/60 bg-ink/5 rounded-md px-3 py-2">
              New Total = {amountParts.map((f) => f.label).join(" + ")} = <span className="font-semibold text-ink tabular">{newTotal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          )}
          {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : isDirect ? "Save Changes" : "Submit for Approval"}</Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
