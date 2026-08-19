import { useAuth } from "../context/AuthContext";
import FinancialDashboard from "./FinancialDashboard";
import EmployeeDashboard from "./EmployeeDashboard";
import ManagerDashboard from "./ManagerDashboard";
import AccountsDashboard from "./AccountsDashboard";

export default function Dashboard() {
  const { user } = useAuth();

  if (user?.role === "EMPLOYEE") return <EmployeeDashboard />;
  if (user?.role === "MANAGER") return <ManagerDashboard />;
  if (user?.role === "ACCOUNTS") return <AccountsDashboard />;
  return <FinancialDashboard />;
}
