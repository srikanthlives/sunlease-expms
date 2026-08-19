import { Link } from "react-router-dom";
import { Card } from "../../components/ui";
import { CalendarDays, TrendingUp, FolderKanban, Building2, Users } from "lucide-react";

const REPORTS = [
  { to: "/reports/daily-register", icon: CalendarDays, title: "Daily Register", desc: "A single day's expenses and payments, broken down by source." },
  { to: "/reports/trend", icon: TrendingUp, title: "Trend Report", desc: "Expense and payment trend over any date range you choose." },
  { to: "/reports/project-wise", icon: FolderKanban, title: "Project-wise", desc: "Spend and outstanding balance by project, over any date range." },
  { to: "/reports/vendor-outstanding", icon: Building2, title: "Vendor Outstanding", desc: "What's owed to each vendor, filterable by project and date range." },
  { to: "/reports/employee-wise", icon: Users, title: "Employee-wise", desc: "Claims, approvals and reimbursement status per employee." },
];

export default function ReportsHub() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Reports</h1>
        <p className="text-sm text-ink/50 mt-0.5">Operational and management reports.</p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {REPORTS.map((r) => (
          <Link key={r.to} to={r.to}>
            <Card className="h-full hover:border-brand-300 hover:shadow-md transition-all cursor-pointer">
              <div className="w-9 h-9 rounded-md bg-brand-50 flex items-center justify-center text-brand-700 mb-3">
                <r.icon size={18} />
              </div>
              <h2 className="font-display font-semibold mb-1">{r.title}</h2>
              <p className="text-xs text-ink/50">{r.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
