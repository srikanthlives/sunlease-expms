import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button, Input } from "../components/ui";
import { apiErrorMessage } from "../api/client";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-11 h-11 rounded-md bg-accent-500 text-white font-display font-semibold text-lg mb-4">
            ₹
          </div>
          <h1 className="text-2xl font-display font-semibold text-white">Ledger</h1>
          <p className="text-white/50 text-sm mt-1">Expense &amp; Payment Management</p>
        </div>
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-card p-6 space-y-4">
          <Input label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="text-white/30 text-xs text-center mt-5">
          Seeded logins — admin/Admin@123 · accounts/Accounts@123 · manager/Manager@123 · ajai/Employee@123
        </p>
      </div>
    </div>
  );
}
