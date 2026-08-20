import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import logo from "../assets/logo.png";
import logoIcon from "../assets/logo_icon.png";
import {
  LayoutDashboard, Receipt, FileText, Wallet, ClipboardList, CheckSquare,
  BarChart3, Users, Building2, Landmark, Tag, Tags, ShieldCheck, LogOut, ScrollText, UserCog, FileEdit,
  ChevronsLeft, ChevronsRight,
} from "lucide-react";

const COLLAPSE_KEY = "expms_sidebar_collapsed";

const NAV = [
  { section: "", items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }] },
  {
    section: "Transactions",
    roles: ["ADMIN", "SUPER_ADMIN", "ACCOUNTS", "VIEWER"],
    items: [
      { to: "/expenses", label: "Expenses", icon: Receipt },
      { to: "/invoices", label: "Invoices", icon: FileText },
      { to: "/payments", label: "Payments", icon: Wallet },
      { to: "/claims", label: "Employee Claims", icon: ClipboardList },
    ],
  },
  {
    section: "My Work",
    roles: ["EMPLOYEE", "MANAGER"],
    items: [{ to: "/my-claims", label: "My Claims", icon: ClipboardList }],
  },
  {
    section: "Approvals",
    roles: ["ADMIN", "SUPER_ADMIN", "MANAGER", "ACCOUNTS"],
    items: [{ to: "/approvals", label: "Claim Approvals", icon: CheckSquare }],
  },
  {
    section: "Edit Requests",
    roles: ["ADMIN", "SUPER_ADMIN", "ACCOUNTS"],
    items: [{ to: "/edit-requests", label: "Review & History", icon: FileEdit }],
  },
  {
    section: "Reports",
    roles: ["ADMIN", "SUPER_ADMIN", "ACCOUNTS", "VIEWER"],
    items: [{ to: "/reports", label: "Reports", icon: BarChart3 }],
  },
  {
    section: "Masters",
    roles: ["ADMIN", "SUPER_ADMIN"],
    items: [
      { to: "/masters/employees", label: "Employees", icon: Users },
      { to: "/masters/vendors", label: "Vendors", icon: Building2 },
      { to: "/masters/projects", label: "Projects", icon: Tag },
      { to: "/masters/accounts", label: "Accounts", icon: Landmark },
      { to: "/masters/categories", label: "Expense Categories", icon: Tags },
    ],
  },
  {
    section: "Administration",
    roles: ["ADMIN", "SUPER_ADMIN"],
    items: [
      { to: "/admin/users", label: "Users & Roles", icon: UserCog },
      { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText },
    ],
  },
];

export default function MainLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");

  function handleLogout() {
    logout();
    navigate("/login");
  }

  function toggleCollapsed() {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, !c ? "1" : "0");
      return !c;
    });
  }

  return (
    <div className="min-h-screen flex bg-[#F7F5F0]">
      <aside className={`shrink-0 bg-ink text-white flex flex-col transition-[width] duration-200 ${collapsed ? "w-16" : "w-60"}`}>
        <div className={`px-5 py-5 flex items-center gap-2.5 border-b border-white/10 ${collapsed ? "px-3 justify-center" : ""}`}>
          {collapsed ? (
            <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center shrink-0 overflow-hidden p-1.5">
              <img src={logoIcon} alt="Sunlease" className="w-full h-full object-contain" />
            </div>
          ) : (
            <div className="w-full rounded-lg bg-white px-3 py-2.5 flex flex-col gap-1">
              <img src={logo} alt="Sunlease" className="h-6 w-auto object-contain self-start" />
              <div className="flex items-baseline gap-1.5">
                <span className="font-display font-semibold text-ink leading-tight text-sm">Ledger</span>
                <span className="text-[9px] text-ink/40 uppercase tracking-wide">Expense &amp; Payments</span>
              </div>
            </div>
          )}
        </div>
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-3 space-y-5">
          {NAV.filter((s) => !s.roles || s.roles.includes(user?.role)).map((section) => (
            <div key={section.section || "root"}>
              {section.section && !collapsed && (
                <div className="text-[10px] uppercase tracking-widest text-white/30 font-medium px-2 mb-1.5">
                  {section.section}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors ${collapsed ? "justify-center" : ""} ${
                        isActive ? "bg-white/10 text-white font-medium" : "text-white/60 hover:bg-white/5 hover:text-white"
                      }`
                    }
                  >
                    <item.icon size={16} strokeWidth={2} />
                    {!collapsed && item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-white/10">
          <button
            onClick={toggleCollapsed}
            className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm text-white/60 hover:bg-white/5 hover:text-white transition-colors ${collapsed ? "justify-center" : ""}`}
            title={collapsed ? "Expand menu" : "Collapse menu"}
          >
            {collapsed ? <ChevronsRight size={16} /> : <><ChevronsLeft size={16} /> Collapse</>}
          </button>
        </div>
        <div className={`p-3 border-t border-white/10 ${collapsed ? "px-2" : ""}`}>
          <div className={`flex items-center gap-2.5 px-2 py-2 ${collapsed ? "justify-center" : ""}`}>
            <div className="w-8 h-8 rounded-full bg-brand-700 flex items-center justify-center text-xs font-semibold shrink-0">
              {user?.full_name?.[0] || user?.username?.[0] || "U"}
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{user?.full_name || user?.username}</div>
                <div className="text-[11px] text-white/40">{user?.role}</div>
              </div>
            )}
            <button onClick={handleLogout} className="text-white/40 hover:text-white p-1" title="Log out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="max-w-[1600px] mx-auto px-8 py-7">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
