import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Card, Table, Button, Input, Select } from "../components/ui";
import { Plus, X, KeyRound, ShieldCheck, ShieldOff, Pencil } from "lucide-react";

export default function UsersAdmin() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "SUPER_ADMIN";

  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [showUserForm, setShowUserForm] = useState(false);
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [editUserTarget, setEditUserTarget] = useState(null);
  const [editRoleTarget, setEditRoleTarget] = useState(null);
  const [error, setError] = useState("");

  function load() {
    client.get("/auth/users").then((res) => setUsers(res.data));
    client.get("/auth/roles").then((res) => setRoles(res.data));
  }
  useEffect(load, []);

  async function toggleActive(u) {
    setError("");
    try {
      await client.post(`/auth/users/${u.id}/set-active`, { is_active: !u.is_active });
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Users &amp; Roles</h1>
          <p className="text-sm text-ink/50 mt-0.5">
            {isSuperAdmin
              ? "Create users, define roles, and reset passwords."
              : "Create and manage users. Role creation and password resets are Super Admin only."}
          </p>
        </div>
        <div className="flex gap-2">
          {isSuperAdmin && <Button variant="outline" onClick={() => setShowRoleForm(true)}><Plus size={16} /> New Role</Button>}
          <Button onClick={() => setShowUserForm(true)}><Plus size={16} /> New User</Button>
        </div>
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {showRoleForm && <RoleForm onClose={() => setShowRoleForm(false)} onCreated={() => { setShowRoleForm(false); load(); }} />}
      {showUserForm && <UserForm roles={roles} isSuperAdmin={isSuperAdmin} onClose={() => setShowUserForm(false)} onCreated={() => { setShowUserForm(false); load(); }} />}
      {resetTarget && <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />}
      {editUserTarget && <EditUserModal user={editUserTarget} onClose={() => setEditUserTarget(null)} onSaved={() => { setEditUserTarget(null); load(); }} />}
      {editRoleTarget && <EditRoleModal role={editRoleTarget} onClose={() => setEditRoleTarget(null)} onSaved={() => { setEditRoleTarget(null); load(); }} />}

      <Card>
        <h2 className="font-display font-semibold text-lg mb-3">Users</h2>
        <Table
          columns={[
            { key: "username", header: "Username" },
            { key: "full_name", header: "Name" },
            { key: "role", header: "Role", render: (r) => <span className="text-xs font-medium bg-ink/5 rounded px-2 py-0.5">{r.role.replace(/_/g, " ")}</span> },
            { key: "is_active", header: "Status", render: (r) => r.is_active ? <span className="text-ok text-xs font-medium">ACTIVE</span> : <span className="text-danger text-xs font-medium">DISABLED</span> },
            {
              key: "actions", header: "Actions",
              render: (r) => (
                <div className="flex items-center gap-2">
                  {(isSuperAdmin || !["ADMIN", "SUPER_ADMIN"].includes(r.role)) && (
                    <button type="button" onClick={() => setEditUserTarget(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline" title="Edit user">
                      <Pencil size={13} /> Edit
                    </button>
                  )}
                  {isSuperAdmin && (
                    <button type="button" onClick={() => setResetTarget(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline" title="Reset password">
                      <KeyRound size={13} /> Reset password
                    </button>
                  )}
                  {r.id !== me?.id && (isSuperAdmin || !["ADMIN", "SUPER_ADMIN"].includes(r.role)) && (
                    <button type="button" onClick={() => toggleActive(r)} className="text-xs inline-flex items-center gap-1 text-ink/50 hover:text-ink" title={r.is_active ? "Disable" : "Enable"}>
                      {r.is_active ? <><ShieldOff size={13} /> Disable</> : <><ShieldCheck size={13} /> Enable</>}
                    </button>
                  )}
                </div>
              ),
            },
          ]}
          rows={users}
        />
      </Card>

      <Card>
        <h2 className="font-display font-semibold text-lg mb-3">Roles</h2>
        <Table
          columns={[
            { key: "name", header: "Role" },
            { key: "description", header: "Description" },
            ...(isSuperAdmin ? [{
              key: "actions", header: "Actions",
              render: (r) => (
                <button type="button" onClick={() => setEditRoleTarget(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline" title="Edit role">
                  <Pencil size={13} /> Edit
                </button>
              ),
            }] : []),
          ]}
          rows={roles}
        />
      </Card>
    </div>
  );
}

function RoleForm({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/auth/roles", { name, description });
      onCreated();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative max-w-md">
      <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
      <h3 className="font-display font-semibold text-lg mb-4">New Role</h3>
      <form onSubmit={submit} className="space-y-4">
        <Input label="Role Name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. AUDITOR" autoFocus />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create Role"}</Button>
      </form>
    </Card>
  );
}

function UserForm({ roles, isSuperAdmin, onClose, onCreated }) {
  const [form, setForm] = useState({ username: "", email: "", full_name: "", password: "", role_id: "", employee_id: "" });
  const [employees, setEmployees] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    client.get("/employees").then((res) => setEmployees(res.data));
  }, []);

  // Only a Super Admin may grant the Admin or Super Admin role - mirrors the
  // server-side guard, so an ordinary Admin never even sees those options.
  const selectableRoles = isSuperAdmin
    ? roles
    : roles.filter((r) => !["ADMIN", "SUPER_ADMIN"].includes(r.name));

  const selectedRole = roles.find((r) => String(r.id) === String(form.role_id));
  const needsEmployeeLink = selectedRole && ["EMPLOYEE", "MANAGER"].includes(selectedRole.name);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/auth/users", {
        ...form, email: form.email || null, role_id: Number(form.role_id),
        employee_id: form.employee_id || null,
      });
      onCreated();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative max-w-md">
      <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
      <h3 className="font-display font-semibold text-lg mb-4">New User</h3>
      <form onSubmit={submit} className="space-y-4">
        <Input label="Username" required value={form.username} onChange={(e) => set("username", e.target.value)} autoFocus />
        <Input label="Full Name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
        <Input label="Email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        <Input label="Password" type="password" required minLength={8} value={form.password} onChange={(e) => set("password", e.target.value)} />
        <Select label="Role" required value={form.role_id} onChange={(e) => set("role_id", e.target.value)}>
          <option value="">Select…</option>
          {selectableRoles.map((r) => <option key={r.id} value={r.id}>{r.name.replace(/_/g, " ")}</option>)}
        </Select>
        {needsEmployeeLink && (
          <Select label="Linked Employee Record" value={form.employee_id} onChange={(e) => set("employee_id", e.target.value)}>
            <option value="">— none —</option>
            {employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.employee_name} ({emp.employee_code})</option>)}
          </Select>
        )}
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create User"}</Button>
      </form>
    </Card>
  );
}

function EditUserModal({ user, onClose, onSaved }) {
  const [form, setForm] = useState({ username: user.username, email: user.email || "", full_name: user.full_name || "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  function buildChanges() {
    const changes = {};
    if (form.username !== user.username) changes.username = form.username;
    if ((form.email || null) !== (user.email || null)) changes.email = form.email || null;
    if ((form.full_name || null) !== (user.full_name || null)) changes.full_name = form.full_name || null;
    return changes;
  }

  async function submit(e) {
    e.preventDefault();
    const changes = buildChanges();
    if (Object.keys(changes).length === 0) { onClose(); return; }
    setBusy(true);
    setError("");
    try {
      await client.put(`/auth/users/${user.id}`, changes);
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-5 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <h3 className="font-display font-semibold text-lg mb-4">Edit User</h3>
        <form onSubmit={submit} className="space-y-4">
          <Input label="Username" required value={form.username} onChange={(e) => set("username", e.target.value)} autoFocus />
          <Input label="Full Name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
          <Input label="Email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Saving…" : "Save Changes"}</Button>
        </form>
      </div>
    </div>
  );
}

function EditRoleModal({ role, onClose, onSaved }) {
  const [form, setForm] = useState({ name: role.name, description: role.description || "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  function buildChanges() {
    const changes = {};
    if (form.name.toUpperCase() !== role.name) changes.name = form.name;
    if ((form.description || null) !== (role.description || null)) changes.description = form.description || null;
    return changes;
  }

  async function submit(e) {
    e.preventDefault();
    const changes = buildChanges();
    if (Object.keys(changes).length === 0) { onClose(); return; }
    setBusy(true);
    setError("");
    try {
      await client.put(`/auth/roles/${role.id}`, changes);
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-5 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <h3 className="font-display font-semibold text-lg mb-4">Edit Role</h3>
        <form onSubmit={submit} className="space-y-4">
          <Input label="Role Name" required value={form.name} onChange={(e) => set("name", e.target.value)} autoFocus />
          <Input label="Description" value={form.description} onChange={(e) => set("description", e.target.value)} />
          {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Saving…" : "Save Changes"}</Button>
        </form>
      </div>
    </div>
  );
}

function ResetPasswordModal({ user, onClose }) {
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post(`/auth/users/${user.id}/reset-password`, { new_password: newPassword });
      setDone(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-5 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <h3 className="font-display font-semibold text-lg mb-1">Reset Password</h3>
        <p className="text-xs text-ink/50 mb-4">For user <span className="font-medium text-ink/70">{user.username}</span></p>

        {done ? (
          <div className="text-sm text-ok bg-ok/10 rounded-md px-3 py-2">
            Password reset. Share the new password with {user.username} through a secure channel.
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Input label="New Password" type="password" required minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoFocus />
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
            <Button type="submit" disabled={busy} className="w-full">{busy ? "Resetting…" : "Reset Password"}</Button>
          </form>
        )}
      </div>
    </div>
  );
}
