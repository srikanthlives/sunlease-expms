import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { Card, StatCard, Button, formatMoney } from "../components/ui";
import FinancialDashboard from "./FinancialDashboard";
import { ArrowRight } from "lucide-react";

export default function AccountsDashboard() {
  const [data, setData] = useState(null);
  const masters = useMasters();
  const navigate = useNavigate();

  useEffect(() => {
    client.get("/dashboard/accounts-approvals").then((res) => setData(res.data));
  }, []);

  const empName = (id) => masters.employees.find((e) => e.id === id)?.employee_name || `Employee #${id}`;
  const projectName = (id) => (id ? masters.projects.find((p) => p.id === id)?.name || `Project #${id}` : "No Project");

  return (
    <div className="space-y-7">
      {data && data.pending_count > 0 && (
        <Card className="border-accent-500/30 bg-accent-500/5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="font-display font-semibold text-lg">Claims Awaiting Your Final Approval</h2>
              <p className="text-xs text-ink/50 mt-0.5">{data.pending_count} claim(s) · {formatMoney(data.pending_total)} total</p>
            </div>
            <Button variant="outline" onClick={() => navigate("/approvals")}>Review all <ArrowRight size={14} /></Button>
          </div>
          <ul className="divide-y divide-ink/10">
            {data.pending_claims.map((c) => (
              <li key={c.id} className="py-2.5 flex items-center justify-between cursor-pointer hover:bg-white/60 -mx-2 px-2 rounded" onClick={() => navigate(`/claims/${c.id}`)}>
                <div>
                  <div className="text-sm font-medium">{c.claim_number}</div>
                  <div className="text-xs text-ink/40">{empName(c.employee_id)} · {projectName(c.project_id)}</div>
                </div>
                <span className="tabular text-sm font-medium">{formatMoney(c.total_amount)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <FinancialDashboard />
    </div>
  );
}
