import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useMasters } from "../hooks/useMasters";
import { Card, Button, Input, StatusBadge, formatMoney, vendorLabel } from "../components/ui";
import { CheckCircle2, XCircle, RefreshCw } from "lucide-react";

export default function RecurringExpenseApprovals() {
  const { user } = useAuth();
  const masters = useMasters();
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [amounts, setAmounts] = useState({});
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  function load() { client.get("/recurring-expenses/instances/pending").then((res) => setRows(res.data)); }
  useEffect(load, []);

  async function submitAccountsReview(row) {
    setError("");
    try {
      const amt = amounts[row.id];
      await client.post(`/recurring-expenses/instances/${row.id}/accounts-review`, {
        amount: amt !== undefined && amt !== "" ? Number(amt) : null,
      });
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function adminApprove(row) {
    setError("");
    try {
      await client.post(`/recurring-expenses/instances/${row.id}/admin-approve`);
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
    if (row.vendor_id) return vendorLabel(masters.vendors.find((v) => v.id === row.vendor_id));
    if (row.employee_id) return masters.employees.find((e) => e.id === row.employee_id)?.employee_name;
    return "—";
  };

  if (masters.loading) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-semibold">Recurring Expense Approvals</h1>
          <p className="text-sm text-ink/50 mt-0.5">
            Bills generated ahead of their due date. Accounts confirms/enters the actual amount first; Admin gives final approval to post it as an Expense.
          </p>
        </div>
        <Button variant="ghost" onClick={load}><RefreshCw size={14} /> Refresh</Button>
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {rows.length === 0 ? (
        <Card><div className="text-sm text-ink/40 py-6 text-center">Nothing pending approval right now.</div></Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row) => {
            const needsAccounts = row.status === "PENDING_ACCOUNTS_REVIEW";
            return (
              <Card key={row.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-sm font-semibold">{row.recurring_expense_name}</span>
                      <StatusBadge status={row.status} />
                      {row.amount_type === "OPEN" && <span className="text-[11px] text-ink/40 italic">Open Amount</span>}
                    </div>
                    <div className="text-xs text-ink/50 mb-2">
                      Bill date {row.occurrence_date}{row.due_date ? ` · Due ${row.due_date}` : ""} · Payee: {payeeName(row)}
                    </div>
                    {needsAccounts ? (
                      <div className="max-w-xs">
                        <Input label={row.amount_type === "OPEN" ? "Enter Bill Amount" : "Amount (correct if changed)"}
                          type="number" step="0.01"
                          defaultValue={row.amount ?? ""}
                          onChange={(e) => setAmounts((s) => ({ ...s, [row.id]: e.target.value }))} />
                      </div>
                    ) : (
                      <div className="text-sm font-medium">{formatMoney(row.amount)}</div>
                    )}
                  </div>
                  <div className="flex flex-col gap-2 shrink-0">
                    {needsAccounts && (
                      <Button variant="accent" onClick={() => submitAccountsReview(row)}>
                        <CheckCircle2 size={14} /> Confirm &amp; Send to Admin
                      </Button>
                    )}
                    {!needsAccounts && isAdmin && (
                      <Button variant="accent" onClick={() => adminApprove(row)}>
                        <CheckCircle2 size={14} /> Approve
                      </Button>
                    )}
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
