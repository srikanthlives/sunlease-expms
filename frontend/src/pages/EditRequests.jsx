import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Card, StatusBadge, Button, Input, formatMoney } from "../components/ui";
import { CheckCircle2, XCircle, Clock } from "lucide-react";

const ENTITY_LABELS = { EXPENSE: "Expense", INVOICE: "Invoice", PAYMENT: "Payment" };

function formatValue(field, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (["base_amount", "gst_amount", "other_amount", "taxable_amount", "cgst", "sgst", "igst", "other_tax"].includes(field)) {
    return formatMoney(value);
  }
  return String(value);
}

function ChangeDiff({ req }) {
  const fields = Object.keys(req.changes);
  return (
    <div className="space-y-1.5">
      {fields.map((f) => (
        <div key={f} className="text-xs flex items-center gap-2">
          <span className="text-ink/40 w-32 shrink-0">{f.replace(/_/g, " ")}</span>
          <span className="text-ink/50 line-through">{formatValue(f, req.previous_values[f])}</span>
          <span className="text-ink/30">→</span>
          <span className="text-ink font-medium">{formatValue(f, req.changes[f])}</span>
        </div>
      ))}
    </div>
  );
}

export default function EditRequests() {
  const { user } = useAuth();
  const isReviewer = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  function load() {
    client.get("/edit-requests").then((res) => setRequests(res.data));
  }
  useEffect(load, []);

  async function approve(id) {
    setError("");
    try {
      await client.post(`/edit-requests/${id}/approve`, {});
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function reject(id) {
    setError("");
    try {
      await client.post(`/edit-requests/${id}/reject`, { reason: rejectReason });
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const pending = requests.filter((r) => r.status === "PENDING");
  const history = requests.filter((r) => r.status !== "PENDING");

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-2xl font-display font-semibold">Edit Requests</h1>
        <p className="text-sm text-ink/50 mt-0.5">
          {isReviewer
            ? "Changes Accounts proposed to posted expenses, invoices and payments — review, and a full history of every decision."
            : "Your proposed edits to posted expenses, invoices and payments, and their approval status."}
        </p>
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {isReviewer && (
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/40 mb-3">
            Pending Review {pending.length > 0 && <span className="text-accent-600">({pending.length})</span>}
          </h2>
          {pending.length === 0 ? (
            <Card><div className="text-sm text-ink/40 py-4 text-center">Nothing pending review.</div></Card>
          ) : (
            <div className="space-y-3">
              {pending.map((req) => (
                <Card key={req.id}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-semibold">{ENTITY_LABELS[req.entity_type]} #{req.entity_id}</span>
                        <StatusBadge status={req.status} />
                      </div>
                      <div className="text-xs text-ink/50 mb-3">
                        Requested by <span className="font-medium text-ink/70">{req.requested_by_name}</span> · {new Date(req.requested_at).toLocaleString()}
                      </div>
                      <ChangeDiff req={req} />
                    </div>
                    <div className="flex flex-col gap-2 shrink-0">
                      <Button variant="accent" onClick={() => approve(req.id)}><CheckCircle2 size={14} /> Approve</Button>
                      <Button variant="danger" onClick={() => setRejectingId(req.id)}><XCircle size={14} /> Reject</Button>
                    </div>
                  </div>
                  {rejectingId === req.id && (
                    <div className="mt-4 pt-4 border-t border-ink/10 flex items-end gap-3">
                      <div className="flex-1">
                        <Input label="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} autoFocus />
                      </div>
                      <Button variant="danger" onClick={() => reject(req.id)}>Confirm Reject</Button>
                      <Button variant="ghost" onClick={() => { setRejectingId(null); setRejectReason(""); }}>Cancel</Button>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {!isReviewer && pending.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/40 mb-3">Awaiting Admin Review</h2>
          <div className="space-y-3">
            {pending.map((req) => (
              <Card key={req.id}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-semibold">{ENTITY_LABELS[req.entity_type]} #{req.entity_id}</span>
                  <StatusBadge status={req.status} />
                  <span className="text-xs text-ink/40 inline-flex items-center gap-1 ml-auto"><Clock size={12} /> {new Date(req.requested_at).toLocaleString()}</span>
                </div>
                <ChangeDiff req={req} />
              </Card>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/40 mb-3">History</h2>
        {history.length === 0 ? (
          <Card><div className="text-sm text-ink/40 py-4 text-center">No decisions yet.</div></Card>
        ) : (
          <div className="space-y-3">
            {history.map((req) => (
              <Card key={req.id} className={req.status === "REJECTED" ? "border-danger/20" : "border-ok/20"}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-semibold">{ENTITY_LABELS[req.entity_type]} #{req.entity_id}</span>
                  <StatusBadge status={req.status} />
                </div>
                <div className="text-xs text-ink/50 mb-3">
                  Requested by <span className="font-medium text-ink/70">{req.requested_by_name}</span> · {new Date(req.requested_at).toLocaleString()}
                  {req.reviewed_by_name && (
                    <> · {req.status === "APPROVED" ? "Approved" : "Rejected"} by <span className="font-medium text-ink/70">{req.reviewed_by_name}</span> · {new Date(req.reviewed_at).toLocaleString()}</>
                  )}
                </div>
                <ChangeDiff req={req} />
                {req.review_remarks && (
                  <div className={`text-xs mt-3 pt-3 border-t border-ink/10 ${req.status === "REJECTED" ? "text-danger" : "text-ink/60"}`}>
                    <span className="font-medium">{req.status === "REJECTED" ? "Reason: " : "Note: "}</span>{req.review_remarks}
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
