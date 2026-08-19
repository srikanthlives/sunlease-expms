import { useEffect, useState } from "react";
import client from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { Card, StatCard, Select, formatMoney } from "../components/ui";
import { FolderKanban, UserCheck } from "lucide-react";

export default function FinancialDashboard({ title = "Dashboard", showHeader = true }) {
  const [data, setData] = useState(null);
  const [projectId, setProjectId] = useState("");
  const masters = useMasters();

  useEffect(() => {
    const params = {};
    if (projectId) params.project_id = projectId;
    setData(null);
    client.get("/dashboard", { params }).then((res) => setData(res.data));
  }, [projectId]);

  const categoryName = (id) => (id ? masters.categories.find((c) => c.id === id)?.name || `Category #${id}` : "Uncategorised");
  const projectName = (id) => (id ? masters.projects.find((p) => p.id === id)?.name || `Project #${id}` : "No Project");

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between flex-wrap gap-4">
        {showHeader && (
          <div>
            <h1 className="text-2xl font-display font-semibold">{title}</h1>
            <p className="text-sm text-ink/50 mt-0.5">{new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</p>
          </div>
        )}
        <Select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-56">
          <option value="">All Projects (Company-wide)</option>
          {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {!data ? (
        <div className="text-sm text-ink/40">Loading…</div>
      ) : (
        <FinancialDashboardBody data={data} categoryName={categoryName} projectName={projectName} onSelectProject={setProjectId} />
      )}
    </div>
  );
}

function FinancialDashboardBody({ data, categoryName, projectName, onSelectProject }) {
  const maxTrend = Math.max(1, ...data.monthly_trend.flatMap((m) => [m.expenses, m.payments]));
  const maxCategoryAmount = Math.max(1, ...data.expense_by_category.map((c) => c.amount));
  const maxProjectAmount = Math.max(1, ...data.expense_by_project.map((p) => p.amount));

  return (
    <>
      {data.project && (
        <Card className="border-brand-200 bg-brand-50/50">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-md bg-white flex items-center justify-center text-brand-700 shrink-0">
                <FolderKanban size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-display font-semibold text-lg">{data.project.name}</h2>
                  <span className="text-xs bg-white border border-ink/10 rounded px-1.5 py-0.5 text-ink/50 font-mono">{data.project.code}</span>
                </div>
                {data.project.description && <p className="text-sm text-ink/50 mt-0.5">{data.project.description}</p>}
                <div className="flex items-center gap-1.5 text-xs text-ink/50 mt-1.5">
                  <UserCheck size={13} />
                  Claim approver: {data.project.accounts_approver_name || <span className="text-warn">unassigned</span>}
                </div>
              </div>
            </div>
            <div className="flex gap-5 text-right">
              <div>
                <div className="text-xs text-ink/40 uppercase tracking-wide">All-Time Expense</div>
                <div className="tabular font-semibold">{formatMoney(data.project.all_time_expense)}</div>
              </div>
              <div>
                <div className="text-xs text-ink/40 uppercase tracking-wide">All-Time Paid</div>
                <div className="tabular font-semibold text-ok">{formatMoney(data.project.all_time_paid)}</div>
              </div>
              <div>
                <div className="text-xs text-ink/40 uppercase tracking-wide">Outstanding</div>
                <div className="tabular font-semibold text-warn">{formatMoney(data.project.all_time_outstanding)}</div>
              </div>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Today's Expenses" value={formatMoney(data.todays_expenses)} />
        <StatCard label="Today's Payments" value={formatMoney(data.todays_payments)} />
        <StatCard label="This Month" value={formatMoney(data.month_expenses)} />
        <StatCard label="Outstanding" value={formatMoney(data.outstanding)} tone="warn" />
        <StatCard label="Pending Claims" value={data.pending_claims} />
        <StatCard label="Pending Approvals" value={data.pending_approvals} />
      </div>

      <Card>
        <h2 className="font-display font-semibold text-lg mb-4">Monthly Trend</h2>
        <div className="flex items-end gap-4 h-40">
          {data.monthly_trend.map((m) => (
            <div key={m.month} className="flex-1 flex flex-col items-center justify-end gap-1 h-full">
              <div className="flex-1 flex items-end gap-1 w-full justify-center">
                <div
                  className="w-3 bg-brand-500 rounded-t"
                  style={{ height: `${(m.expenses / maxTrend) * 100}%`, minHeight: 2 }}
                  title={`Expenses: ${formatMoney(m.expenses)}`}
                />
                <div
                  className="w-3 bg-accent-500 rounded-t"
                  style={{ height: `${(m.payments / maxTrend) * 100}%`, minHeight: 2 }}
                  title={`Payments: ${formatMoney(m.payments)}`}
                />
              </div>
              <div className="text-[10px] text-ink/40 tabular">{m.month.slice(5)}</div>
            </div>
          ))}
        </div>
        <div className="flex gap-4 mt-4 text-xs text-ink/50">
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-brand-500" /> Expenses</div>
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-accent-500" /> Payments</div>
        </div>
      </Card>

      <div className={data.project ? "grid gap-5" : "grid md:grid-cols-2 gap-5"}>
        <Card>
          <h2 className="font-display font-semibold text-lg mb-3">Expense by Category</h2>
          {data.expense_by_category.length === 0 ? (
            <p className="text-sm text-ink/40">No expenses this month yet.</p>
          ) : (
            <ul className="space-y-3">
              {data.expense_by_category
                .slice()
                .sort((a, b) => b.amount - a.amount)
                .map((c) => (
                  <li key={c.category_id ?? "none"}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-ink/70">{categoryName(c.category_id)}</span>
                      <span className="tabular font-medium">{formatMoney(c.amount)}</span>
                    </div>
                    <div className="h-1.5 bg-ink/5 rounded-full overflow-hidden">
                      <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(c.amount / maxCategoryAmount) * 100}%` }} />
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </Card>
        {!data.project && (
          <Card>
            <h2 className="font-display font-semibold text-lg mb-3">Expense by Project</h2>
            {data.expense_by_project.length === 0 ? (
              <p className="text-sm text-ink/40">No expenses this month yet.</p>
            ) : (
              <ul className="space-y-3">
                {data.expense_by_project
                  .slice()
                  .sort((a, b) => b.amount - a.amount)
                  .map((p) => (
                    <li key={p.project_id ?? "none"}>
                      <button
                        type="button"
                        onClick={() => p.project_id && onSelectProject(String(p.project_id))}
                        className={`w-full text-left ${p.project_id ? "cursor-pointer hover:opacity-70" : "cursor-default"}`}
                        disabled={!p.project_id}
                      >
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-ink/70">{projectName(p.project_id)}</span>
                          <span className="tabular font-medium">{formatMoney(p.amount)}</span>
                        </div>
                        <div className="h-1.5 bg-ink/5 rounded-full overflow-hidden">
                          <div className="h-full bg-accent-500 rounded-full" style={{ width: `${(p.amount / maxProjectAmount) * 100}%` }} />
                        </div>
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
