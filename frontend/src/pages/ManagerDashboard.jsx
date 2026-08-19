import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, StatCard, StatusBadge, Button, formatMoney } from "../components/ui";
import { ArrowRight, Plus } from "lucide-react";

const STATUS_ORDER = ["DRAFT", "SUBMITTED", "PENDING_ACCOUNTS_APPROVAL", "APPROVED", "REJECTED", "CANCELLED"];

export default function ManagerDashboard() {
  const { user } = useAuth();
  const [approvals, setApprovals] = useState(null);
  const [myClaims, setMyClaims] = useState(null);
  const masters = useMasters();
  const navigate = useNavigate();

  useEffect(() => {
    client.get("/dashboard/approvals").then((res) => setApprovals(res.data));
    client.get("/dashboard/my-claims").then((res) => setMyClaims(res.data));
  }, []);

  const empName = (id) => masters.employees.find((e) => e.id === id)?.employee_name || `Employee #${id}`;

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-2xl font-display font-semibold">Welcome back, {user?.full_name?.split(" ")[0] || user?.username}</h1>
        <p className="text-sm text-ink/50 mt-0.5">Approvals for your team, and your own claims.</p>
      </div>

      {approvals && (
        <>
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/40 mb-3">Your Team's Approvals</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Pending Your Approval" value={approvals.pending_count} tone={approvals.pending_count > 0 ? "warn" : "ink"} />
              <StatCard label="Pending Value" value={formatMoney(approvals.pending_total)} />
              <StatCard label="Approved (30d)" value={approvals.recently_approved_30d} tone="ok" />
              <StatCard label="Rejected (30d)" value={approvals.recently_rejected_30d} />
            </div>
          </div>

          <Card>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display font-semibold text-lg">Awaiting Your Review</h2>
              {approvals.pending_claims.length > 0 && (
                <Button variant="outline" onClick={() => navigate("/approvals")}>Review all <ArrowRight size={14} /></Button>
              )}
            </div>
            {approvals.pending_claims.length === 0 ? (
              <p className="text-sm text-ink/40">Nothing waiting on you right now.</p>
            ) : (
              <ul className="divide-y divide-ink/5">
                {approvals.pending_claims.map((c) => (
                  <li key={c.id} className="py-2.5 flex items-center justify-between cursor-pointer hover:bg-brand-50 -mx-2 px-2 rounded" onClick={() => navigate(`/claims/${c.id}`)}>
                    <div>
                      <div className="text-sm font-medium">{c.claim_number}</div>
                      <div className="text-xs text-ink/40">{empName(c.employee_id)}</div>
                    </div>
                    <span className="tabular text-sm font-medium">{formatMoney(c.total_amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      {myClaims && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/40">Your Own Claims</h2>
            <Button onClick={() => navigate("/my-claims")}><Plus size={14} /> New Claim</Button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <StatCard label="Total Claims" value={myClaims.total_claims} />
            <StatCard label="Total Claimed" value={formatMoney(myClaims.total_claimed)} />
            <StatCard label="Reimbursed" value={formatMoney(myClaims.total_paid)} tone="ok" />
            <StatCard label="Owed to Me" value={formatMoney(myClaims.total_owed_to_me)} tone="warn" />
          </div>
          {myClaims.total_claims > 0 && (
            <Card>
              <div className="flex flex-wrap gap-3">
                {STATUS_ORDER.filter((s) => myClaims.by_status[s]).map((s) => (
                  <div key={s} className="flex items-center gap-2 bg-ink/5 rounded-md px-3 py-2">
                    <StatusBadge status={s} />
                    <span className="text-sm font-semibold tabular">{myClaims.by_status[s]}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
