import { useEffect, useRef, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Card, Table, Button, Input, Select } from "../components/ui";
import { Plus, X, KeyRound, ShieldCheck, ShieldOff, Pencil, AlertTriangle } from "lucide-react";

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
      {editUserTarget && <EditUserModal user={editUserTarget} roles={roles} onClose={() => setEditUserTarget(null)} onSaved={() => { setEditUserTarget(null); load(); }} />}
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

      {isSuperAdmin && <DatabaseBackupCard />}
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

function EditUserModal({ user, roles, onClose, onSaved }) {
  const currentRole = roles.find((r) => r.name === user.role);
  const [form, setForm] = useState({ username: user.username, email: user.email || "", full_name: user.full_name || "", role_id: currentRole?.id || "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  // Only Employee <-> Manager switching is supported (mirrors the backend
  // guard) - Admin/Accounts/etc still need a new account, not a role edit.
  const canSwitchRole = ["EMPLOYEE", "MANAGER"].includes(user.role);
  const switchableRoles = roles.filter((r) => ["EMPLOYEE", "MANAGER"].includes(r.name));

  function buildChanges() {
    const changes = {};
    if (form.username !== user.username) changes.username = form.username;
    if ((form.email || null) !== (user.email || null)) changes.email = form.email || null;
    if ((form.full_name || null) !== (user.full_name || null)) changes.full_name = form.full_name || null;
    if (canSwitchRole && form.role_id && Number(form.role_id) !== currentRole?.id) changes.role_id = Number(form.role_id);
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
          {canSwitchRole && (
            <Select label="Role" value={form.role_id} onChange={(e) => set("role_id", e.target.value)}>
              {switchableRoles.map((r) => <option key={r.id} value={r.id}>{r.name.replace(/_/g, " ")}</option>)}
            </Select>
          )}
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

function DatabaseBackupCard() {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [showRestore, setShowRestore] = useState(false);
  const fileInputRef = useRef(null);

  async function download() {
    setDownloading(true);
    setError("");
    try {
      const res = await client.get("/admin/db-backup", { responseType: "blob" });
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : `expms-backup-${new Date().toISOString().slice(0, 10)}.db`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      // responseType: "blob" means even a JSON error body arrives as a Blob,
      // so apiErrorMessage's err.response.data.detail lookup would miss it -
      // decode it back to text first.
      if (err?.response?.data instanceof Blob && err.response.data.type.includes("json")) {
        try {
          const text = await err.response.data.text();
          setError(JSON.parse(text).detail || apiErrorMessage(err));
        } catch {
          setError(apiErrorMessage(err));
        }
      } else {
        setError(apiErrorMessage(err));
      }
    } finally {
      setDownloading(false);
    }
  }

  function handleFileSelected(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setPendingFile(file);
    setShowRestore(true);
  }

  return (
    <Card>
      <h2 className="font-display font-semibold text-lg mb-1">Database Backup &amp; Restore</h2>
      <p className="text-xs text-ink/50 mb-4">
        Download a full copy of the live database, or replace it with a previously downloaded backup. Useful on
        platforms like Railway with no direct file access to the mounted volume.
      </p>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
      <div className="flex gap-2">
        <Button type="button" onClick={download} disabled={downloading}>
          {downloading ? "Preparing…" : "Download Backup"}
        </Button>
        <input ref={fileInputRef} type="file" accept=".db,.sqlite,.sqlite3" className="hidden" onChange={handleFileSelected} />
        <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
          Upload &amp; Restore…
        </Button>
      </div>
      {showRestore && pendingFile && (
        <RestoreConfirmModal
          file={pendingFile}
          onClose={() => { setShowRestore(false); setPendingFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
        />
      )}
    </Card>
  );
}

function RestoreConfirmModal({ file, onClose }) {
  const [step, setStep] = useState(1);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("confirm", confirmText);
      await client.post("/admin/db-restore", form, { headers: { "Content-Type": "multipart/form-data" } });
      setDone(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/50 z-40 flex items-center justify-center p-4" onClick={busy ? undefined : onClose}>
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-md p-5 relative" onClick={(e) => e.stopPropagation()}>
        {!busy && <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>}
        <div className="flex items-center gap-2 mb-2 text-danger">
          <AlertTriangle size={18} />
          <h3 className="font-display font-semibold text-lg">
            {done ? "Database restored" : step === 1 ? "Replace the live database?" : "Type REPLACE to confirm"}
          </h3>
        </div>

        {done ? (
          <>
            <p className="text-sm text-ink/60 mb-5">
              The database has been replaced with <span className="font-medium text-ink/80">{file.name}</span>. A
              backup of the previous database was saved alongside it on the server.
            </p>
            <Button type="button" onClick={onClose} className="w-full">Close</Button>
          </>
        ) : step === 1 ? (
          <>
            <p className="text-sm text-ink/60 mb-5">
              This will overwrite the entire live database with <span className="font-medium text-ink/80">{file.name}</span>.
              Every expense, invoice, payment, and claim currently in the app will be replaced by whatever was in that
              file at the time it was downloaded. This cannot be undone from the app itself.
            </p>
            <div className="flex gap-2">
              <Button type="button" variant="danger" onClick={() => setStep(2)} className="flex-1">Continue</Button>
              <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-ink/60 mb-3">
              Last chance - type <span className="font-mono font-semibold text-ink">REPLACE</span> below to actually
              overwrite the database.
            </p>
            <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="REPLACE" autoFocus />
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mt-3">{error}</div>}
            <div className="flex gap-2 mt-4">
              <Button type="button" variant="danger" disabled={busy || confirmText !== "REPLACE"} onClick={submit} className="flex-1">
                {busy ? "Restoring…" : "Permanently replace database"}
              </Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={onClose}>Cancel</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
