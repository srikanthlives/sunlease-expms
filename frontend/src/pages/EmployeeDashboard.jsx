import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Card, StatCard, StatusBadge, Button, formatMoney } from "../components/ui";
import { Plus } from "lucide-react";

const STATUS_ORDER = ["DRAFT", "SUBMITTED", "PENDING_ACCOUNTS_APPROVAL", "APPROVED", "REJECTED", "CANCELLED"];

export default function EmployeeDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    client.get("/dashboard/my-claims").then((res) => setData(res.data));
  }, []);

  if (!data) return <div className="text-sm text-ink/40">Loading…</div>;

  return (
    <div className="space-y-7">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Welcome back, {user?.full_name?.split(" ")[0] || user?.username}</h1>
          <p className="text-sm text-ink/50 mt-0.5">Your claims and reimbursement status.</p>
        </div>
        <Button onClick={() => navigate("/my-claims")}><Plus size={16} /> New Claim</Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Claims" value={data.total_claims} />
        <StatCard label="Total Claimed" value={formatMoney(data.total_claimed)} />
        <StatCard label="Reimbursed" value={formatMoney(data.total_paid)} tone="ok" />
        <StatCard label="Owed to Me" value={formatMoney(data.total_owed_to_me)} tone="warn" />
      </div>

      <Card>
        <h2 className="font-display font-semibold text-lg mb-4">Claims by Status</h2>
        {data.total_claims === 0 ? (
          <p className="text-sm text-ink/40">You haven't submitted any claims yet.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {STATUS_ORDER.filter((s) => data.by_status[s]).map((s) => (
              <div key={s} className="flex items-center gap-2 bg-ink/5 rounded-md px-3 py-2">
                <StatusBadge status={s} />
                <span className="text-sm font-semibold tabular">{data.by_status[s]}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display font-semibold text-lg">Recent Claims</h2>
          <button onClick={() => navigate("/my-claims")} className="text-xs text-brand-600 hover:underline">View all →</button>
        </div>
        {data.recent_claims.length === 0 ? (
          <p className="text-sm text-ink/40">No claims yet — submit your first one to get reimbursed.</p>
        ) : (
          <ul className="divide-y divide-ink/5">
            {data.recent_claims.map((c) => (
              <li key={c.id} className="py-2.5 flex items-center justify-between cursor-pointer hover:bg-brand-50 -mx-2 px-2 rounded" onClick={() => navigate(`/claims/${c.id}`)}>
                <div>
                  <div className="text-sm font-medium">{c.claim_number}</div>
                  <div className="text-xs text-ink/40">{c.claim_date}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular text-sm">{formatMoney(c.total_amount)}</span>
                  <StatusBadge status={c.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
