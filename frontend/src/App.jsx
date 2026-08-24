import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import MainLayout from "./layouts/MainLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Expenses from "./pages/Expenses";
import Invoices from "./pages/Invoices";
import Payments from "./pages/Payments";
import { ClaimsList, ClaimDetail } from "./pages/Claims";
import ReportsHub from "./pages/reports/ReportsHub";
import DailyRegisterReport from "./pages/reports/DailyRegisterReport";
import TrendReport from "./pages/reports/TrendReport";
import ProjectWiseReport from "./pages/reports/ProjectWiseReport";
import VendorOutstandingReport from "./pages/reports/VendorOutstandingReport";
import EmployeeWiseReport from "./pages/reports/EmployeeWiseReport";
import { EmployeesMaster, VendorsMaster, ProjectsMaster, AccountsMaster, CategoriesMaster } from "./pages/Masters";
import AuditLogs from "./pages/AuditLogs";
import UsersAdmin from "./pages/UsersAdmin";
import EditRequests from "./pages/EditRequests";
import RecurringExpenses from "./pages/RecurringExpenses";
import RecurringExpenseApprovals from "./pages/RecurringExpenseApprovals";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-ink/40 text-sm">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="expenses" element={<Expenses />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="payments" element={<Payments />} />
            <Route path="claims" element={<ClaimsList />} />
            <Route path="claims/:id" element={<ClaimDetail />} />
            <Route path="my-claims" element={<ClaimsList mineOnly />} />
            <Route path="approvals" element={<ClaimsList approvalsOnly />} />
            <Route path="reports" element={<ReportsHub />} />
            <Route path="reports/daily-register" element={<DailyRegisterReport />} />
            <Route path="reports/trend" element={<TrendReport />} />
            <Route path="reports/project-wise" element={<ProjectWiseReport />} />
            <Route path="reports/vendor-outstanding" element={<VendorOutstandingReport />} />
            <Route path="reports/employee-wise" element={<EmployeeWiseReport />} />
            <Route path="masters/employees" element={<EmployeesMaster />} />
            <Route path="masters/vendors" element={<VendorsMaster />} />
            <Route path="masters/projects" element={<ProjectsMaster />} />
            <Route path="masters/accounts" element={<AccountsMaster />} />
            <Route path="masters/categories" element={<CategoriesMaster />} />
            <Route path="admin/audit-logs" element={<AuditLogs />} />
            <Route path="admin/users" element={<UsersAdmin />} />
            <Route path="edit-requests" element={<EditRequests />} />
            <Route path="recurring-expenses" element={<RecurringExpenses />} />
            <Route path="recurring-expenses/approvals" element={<RecurringExpenseApprovals />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
