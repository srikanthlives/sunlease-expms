import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Table, Button, Input, Select } from "../components/ui";
import { Plus, X, Pencil } from "lucide-react";

function emptyForm(fields) {
  return Object.fromEntries(fields.map((f) => [f.key, f.default || ""]));
}

function MasterPage({ title, subtitle, endpoint, columns, fields, idField = "id" }) {
  const [rows, setRows] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating, else editing this row's id
  const [form, setForm] = useState(emptyForm(fields));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() { client.get(endpoint).then((res) => setRows(res.data)); }
  useEffect(load, []);

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm(fields));
    setError("");
    setShowForm(true);
  }

  function openEdit(row) {
    setEditingId(row[idField]);
    setForm(Object.fromEntries(fields.map((f) => [f.key, row[f.key] ?? f.default ?? ""])));
    setError("");
    setShowForm(true);
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editingId != null) {
        await client.put(`${endpoint}/${editingId}`, form);
      } else {
        await client.post(endpoint, form);
      }
      setShowForm(false);
      setForm(emptyForm(fields));
      setEditingId(null);
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const editColumns = [
    ...columns,
    {
      key: "__edit", header: "",
      render: (row) => (
        <button type="button" onClick={() => openEdit(row)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
          <Pencil size={12} /> Edit
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">{title}</h1>
          {subtitle && <p className="text-sm text-ink/50 mt-0.5">{subtitle}</p>}
        </div>
        <Button onClick={openCreate}><Plus size={16} /> Add</Button>
      </div>

      {showForm && (
        <Card className="relative">
          <button onClick={() => setShowForm(false)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h2 className="font-display font-semibold text-lg mb-4">{editingId != null ? "Edit" : "New"} {title.replace(/s$/, "")}</h2>
          <form onSubmit={submit} className="space-y-4 max-w-lg">
            <div className="grid grid-cols-2 gap-4">
              {fields.map((f) => (
                <Input key={f.key} label={f.label} required={f.required}
                  value={form[f.key]} onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))} />
              ))}
            </div>
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : editingId != null ? "Save Changes" : "Save"}</Button>
          </form>
        </Card>
      )}

      <Card><Table columns={editColumns} rows={rows} keyField={idField} /></Card>
    </div>
  );
}

export function EmployeesMaster() {
  const [employees, setEmployees] = useState([]);
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const emptyForm = { employee_code: "", employee_name: "", designation: "", department: "", project_id: "", manager_id: "", email: "", phone: "" };
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    client.get("/employees").then((res) => setEmployees(res.data));
    client.get("/projects").then((res) => setProjects(res.data));
  }
  useEffect(load, []);

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setError("");
    setShowForm(true);
  }

  function openEdit(emp) {
    setEditingId(emp.id);
    setForm({
      employee_code: emp.employee_code, employee_name: emp.employee_name,
      designation: emp.designation || "", department: emp.department || "",
      project_id: emp.project_id || "", manager_id: emp.manager_id || "",
      email: emp.email || "", phone: emp.phone || "",
    });
    setError("");
    setShowForm(true);
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = { ...form, project_id: form.project_id || null, manager_id: form.manager_id || null };
      if (editingId != null) {
        await client.put(`/employees/${editingId}`, payload);
      } else {
        await client.post("/employees", payload);
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const projectName = (id) => projects.find((p) => p.id === id)?.name || "—";
  const managerName = (id) => employees.find((e) => e.id === id)?.employee_name || "—";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Employees</h1>
          <p className="text-sm text-ink/50 mt-0.5">Employee master, project assignment, and manager hierarchy (who approves whose claims).</p>
        </div>
        <Button onClick={openCreate}><Plus size={16} /> Add Employee</Button>
      </div>

      {showForm && (
        <Card className="relative">
          <button onClick={() => setShowForm(false)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h2 className="font-display font-semibold text-lg mb-4">{editingId != null ? "Edit Employee" : "New Employee"}</h2>
          <form onSubmit={submit} className="space-y-4 max-w-lg">
            <div className="grid grid-cols-2 gap-4">
              <Input label="Employee Code" required value={form.employee_code} onChange={(e) => setForm((s) => ({ ...s, employee_code: e.target.value }))} />
              <Input label="Full Name" required value={form.employee_name} onChange={(e) => setForm((s) => ({ ...s, employee_name: e.target.value }))} />
              <Input label="Designation" value={form.designation} onChange={(e) => setForm((s) => ({ ...s, designation: e.target.value }))} />
              <Input label="Department" value={form.department} onChange={(e) => setForm((s) => ({ ...s, department: e.target.value }))} />
              <Select label="Project" value={form.project_id} onChange={(e) => setForm((s) => ({ ...s, project_id: e.target.value }))}>
                <option value="">— none —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
              <Select label="Manager" value={form.manager_id} onChange={(e) => setForm((s) => ({ ...s, manager_id: e.target.value }))}>
                <option value="">— none (top-level) —</option>
                {employees.filter((emp) => emp.id !== editingId).map((emp) => <option key={emp.id} value={emp.id}>{emp.employee_name}</option>)}
              </Select>
              <Input label="Email" type="email" value={form.email} onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))} />
              <Input label="Phone" value={form.phone} onChange={(e) => setForm((s) => ({ ...s, phone: e.target.value }))} />
            </div>
            <p className="text-xs text-ink/40">
              Assigning a Manager here determines who does first-level approval on this employee's claims. After creating the employee, link a login for them from Administration → Users &amp; Roles.
            </p>
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : editingId != null ? "Save Changes" : "Save"}</Button>
          </form>
        </Card>
      )}

      <Card>
        <Table
          columns={[
            { key: "employee_code", header: "Code" },
            { key: "employee_name", header: "Name" },
            { key: "designation", header: "Designation" },
            { key: "project_id", header: "Project", render: (r) => projectName(r.project_id) },
            { key: "manager_id", header: "Manager", render: (r) => managerName(r.manager_id) },
            { key: "status", header: "Status" },
            {
              key: "__edit", header: "",
              render: (r) => (
                <button type="button" onClick={() => openEdit(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
                  <Pencil size={12} /> Edit
                </button>
              ),
            },
          ]}
          rows={employees}
        />
      </Card>
    </div>
  );
}

export function VendorsMaster() {
  return (
    <MasterPage
      title="Vendors" subtitle="Supplier / vendor master." endpoint="/vendors"
      columns={[
        { key: "vendor_code", header: "Code" }, { key: "vendor_name", header: "Name" },
        { key: "gstin", header: "GSTIN" }, { key: "phone", header: "Phone" },
      ]}
      fields={[
        { key: "vendor_code", label: "Vendor Code", required: true },
        { key: "vendor_name", label: "Vendor Name", required: true },
        { key: "gstin", label: "GSTIN" },
        { key: "phone", label: "Phone" },
        { key: "email", label: "Email" },
      ]}
    />
  );
}

export function ProjectsMaster() {
  const [projects, setProjects] = useState([]);
  const [accountsUsers, setAccountsUsers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ code: "", name: "", description: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [assigningFor, setAssigningFor] = useState(null); // project id
  const [assignError, setAssignError] = useState("");
  const [assigningAccountsFor, setAssigningAccountsFor] = useState(null); // project id
  const [accountsSelection, setAccountsSelection] = useState([]);

  function load() {
    client.get("/projects").then((res) => setProjects(res.data));
    client.get("/auth/users").then((res) => setAccountsUsers(res.data.filter((u) => ["ACCOUNTS", "ADMIN", "SUPER_ADMIN"].includes(u.role))));
  }
  useEffect(load, []);

  function openCreate() {
    setEditingId(null);
    setForm({ code: "", name: "", description: "" });
    setError("");
    setShowForm(true);
  }

  function openEdit(project) {
    setEditingId(project.id);
    setForm({ code: project.code, name: project.name, description: project.description || "" });
    setError("");
    setShowForm(true);
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editingId != null) {
        await client.put(`/projects/${editingId}`, form);
      } else {
        await client.post("/projects", form);
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ code: "", name: "", description: "" });
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function assignApprover(projectId, userId) {
    setAssignError("");
    try {
      await client.post(`/projects/${projectId}/assign-approver`, { user_id: userId || null });
      setAssigningFor(null);
      load();
    } catch (err) {
      setAssignError(apiErrorMessage(err));
    }
  }

  const approverName = (id) => accountsUsers.find((u) => u.id === id)?.full_name || accountsUsers.find((u) => u.id === id)?.username || "— unassigned —";

  function userLabel(id) {
    const u = accountsUsers.find((x) => x.id === id);
    return u ? (u.full_name || u.username) : id;
  }

  function openAssignAccountsUsers(project) {
    setAssigningAccountsFor(project.id);
    setAccountsSelection(project.accounts_user_ids || []);
  }

  async function saveAccountsUsers(projectId) {
    setAssignError("");
    try {
      await client.post(`/projects/${projectId}/assign-accounts-users`, { user_ids: accountsSelection });
      setAssigningAccountsFor(null);
      load();
    } catch (err) {
      setAssignError(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Projects</h1>
          <p className="text-sm text-ink/50 mt-0.5">Projects / cost centres, and who does final (second-level) claim approval for each.</p>
        </div>
        <Button onClick={openCreate}><Plus size={16} /> Add Project</Button>
      </div>

      {showForm && (
        <Card className="relative max-w-lg">
          <button onClick={() => setShowForm(false)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h2 className="font-display font-semibold text-lg mb-4">{editingId != null ? "Edit Project" : "New Project"}</h2>
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Input label="Project Code" required value={form.code} onChange={(e) => setForm((s) => ({ ...s, code: e.target.value }))} />
              <Input label="Project Name" required value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} />
            </div>
            <Input label="Description" value={form.description} onChange={(e) => setForm((s) => ({ ...s, description: e.target.value }))} />
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : editingId != null ? "Save Changes" : "Save"}</Button>
          </form>
        </Card>
      )}

      {assignError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{assignError}</div>}

      {assigningAccountsFor != null && (
        <Card className="relative max-w-lg">
          <button onClick={() => setAssigningAccountsFor(null)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h2 className="font-display font-semibold text-lg mb-1">Assign Accounts Users</h2>
          <p className="text-sm text-ink/50 mb-4">
            Only these users (role Accounts/Admin/Super Admin) can see or act on this project's expenses, invoices, payments and claims.
            An Accounts user with no projects assigned sees nothing.
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {accountsUsers.map((u) => (
              <label key={u.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={accountsSelection.includes(u.id)}
                  onChange={(e) =>
                    setAccountsSelection((sel) =>
                      e.target.checked ? [...sel, u.id] : sel.filter((id) => id !== u.id)
                    )
                  }
                />
                {u.full_name || u.username} ({u.role})
              </label>
            ))}
          </div>
          <Button className="mt-4" onClick={() => saveAccountsUsers(assigningAccountsFor)}>Save</Button>
        </Card>
      )}

      <Card>
        <Table
          columns={[
            { key: "code", header: "Code" },
            { key: "name", header: "Name" },
            { key: "description", header: "Description" },
            {
              key: "approver", header: "Claim Approver (Accounts)",
              render: (r) =>
                assigningFor === r.id ? (
                  <select
                    autoFocus defaultValue={r.accounts_approver_id || ""}
                    onChange={(e) => assignApprover(r.id, e.target.value ? Number(e.target.value) : null)}
                    onBlur={() => setAssigningFor(null)}
                    className="text-xs rounded border border-ink/15 px-2 py-1"
                  >
                    <option value="">— unassigned —</option>
                    {accountsUsers.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.username} ({u.role})</option>)}
                  </select>
                ) : (
                  <button type="button" onClick={() => setAssigningFor(r.id)} className="text-xs text-brand-700 hover:underline">
                    {approverName(r.accounts_approver_id)}
                  </button>
                ),
            },
            {
              key: "accounts_access", header: "Accounts Access",
              render: (r) => (
                <button type="button" onClick={() => openAssignAccountsUsers(r)} className="text-xs text-brand-700 hover:underline">
                  {(r.accounts_user_ids || []).length > 0
                    ? (r.accounts_user_ids || []).map(userLabel).join(", ")
                    : "— none assigned —"}
                </button>
              ),
            },
            {
              key: "__edit", header: "",
              render: (r) => (
                <button type="button" onClick={() => openEdit(r)} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline">
                  <Pencil size={12} /> Edit
                </button>
              ),
            },
          ]}
          rows={projects}
        />
      </Card>
    </div>
  );
}

export function AccountsMaster() {
  return (
    <MasterPage
      title="Accounts" subtitle="Bank, cash, UPI and petty cash accounts." endpoint="/accounts"
      columns={[{ key: "account_name", header: "Account" }, { key: "account_type", header: "Type" }, { key: "bank_name", header: "Bank" }]}
      fields={[
        { key: "account_name", label: "Account Name", required: true },
        { key: "account_type", label: "Type (BANK/CASH/UPI/PETTY_CASH)", required: true, default: "BANK" },
        { key: "bank_name", label: "Bank Name" },
        { key: "account_number", label: "Account Number" },
        { key: "ifsc", label: "IFSC" },
      ]}
    />
  );
}

export function CategoriesMaster() {
  const [categories, setCategories] = useState([]);
  const [subCategoriesByCategory, setSubCategoriesByCategory] = useState({});
  const [showCatForm, setShowCatForm] = useState(false);
  const [editingCatId, setEditingCatId] = useState(null);
  const [catName, setCatName] = useState("");
  const [catError, setCatError] = useState("");
  const [catBusy, setCatBusy] = useState(false);

  const [subFormForCategory, setSubFormForCategory] = useState(null); // category id or null
  const [editingSub, setEditingSub] = useState(null); // { categoryId, subId } or null
  const [subName, setSubName] = useState("");
  const [subError, setSubError] = useState("");
  const [subBusy, setSubBusy] = useState(false);

  function loadCategories() {
    client.get("/categories").then((res) => {
      setCategories(res.data);
      res.data.forEach((c) => loadSubCategories(c.id));
    });
  }
  function loadSubCategories(categoryId) {
    client.get(`/categories/${categoryId}/sub-categories`).then((res) => {
      setSubCategoriesByCategory((s) => ({ ...s, [categoryId]: res.data }));
    });
  }
  useEffect(loadCategories, []);

  function openCreateCategory() {
    setEditingCatId(null);
    setCatName("");
    setCatError("");
    setShowCatForm(true);
  }

  function openEditCategory(cat) {
    setEditingCatId(cat.id);
    setCatName(cat.name);
    setCatError("");
    setShowCatForm(true);
  }

  async function submitCategory(e) {
    e.preventDefault();
    setCatBusy(true);
    setCatError("");
    try {
      if (editingCatId != null) {
        await client.put(`/categories/${editingCatId}`, { name: catName });
      } else {
        await client.post("/categories", { name: catName });
      }
      setCatName("");
      setEditingCatId(null);
      setShowCatForm(false);
      loadCategories();
    } catch (err) {
      setCatError(apiErrorMessage(err));
    } finally {
      setCatBusy(false);
    }
  }

  function openAddSub(categoryId) {
    setEditingSub(null);
    setSubName("");
    setSubError("");
    setSubFormForCategory(categoryId);
  }

  function openEditSub(categoryId, sub) {
    setEditingSub({ categoryId, subId: sub.id });
    setSubName(sub.name);
    setSubError("");
    setSubFormForCategory(categoryId);
  }

  async function submitSubCategory(e, categoryId) {
    e.preventDefault();
    setSubBusy(true);
    setSubError("");
    try {
      if (editingSub != null) {
        await client.put(`/categories/${categoryId}/sub-categories/${editingSub.subId}`, { category_id: categoryId, name: subName });
      } else {
        await client.post(`/categories/${categoryId}/sub-categories`, { category_id: categoryId, name: subName });
      }
      setSubName("");
      setSubFormForCategory(null);
      setEditingSub(null);
      loadSubCategories(categoryId);
    } catch (err) {
      setSubError(apiErrorMessage(err));
    } finally {
      setSubBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">Expense Categories</h1>
          <p className="text-sm text-ink/50 mt-0.5">Expense heads and their sub-categories, used across expenses, invoices and claims.</p>
        </div>
        <Button onClick={openCreateCategory}><Plus size={16} /> Add Category</Button>
      </div>

      {showCatForm && (
        <Card className="relative max-w-md">
          <button onClick={() => setShowCatForm(false)} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
          <h2 className="font-display font-semibold text-lg mb-4">{editingCatId != null ? "Edit Category" : "New Category"}</h2>
          <form onSubmit={submitCategory} className="space-y-4">
            <Input label="Category Name" required value={catName} onChange={(e) => setCatName(e.target.value)} autoFocus />
            {catError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{catError}</div>}
            <Button type="submit" disabled={catBusy}>{catBusy ? "Saving…" : editingCatId != null ? "Save Changes" : "Save"}</Button>
          </form>
        </Card>
      )}

      <div className="space-y-4">
        {categories.length === 0 && (
          <Card><div className="text-sm text-ink/40 py-4 text-center">No categories yet — add one above.</div></Card>
        )}
        {categories.map((cat) => (
          <Card key={cat.id}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold">{cat.name}</h3>
                <button type="button" onClick={() => openEditCategory(cat)} className="text-ink/30 hover:text-brand-700" title="Edit category name">
                  <Pencil size={13} />
                </button>
              </div>
              <Button variant="outline" onClick={() => (subFormForCategory === cat.id ? setSubFormForCategory(null) : openAddSub(cat.id))}>
                <Plus size={14} /> Add Sub-category
              </Button>
            </div>

            {subFormForCategory === cat.id && (
              <form onSubmit={(e) => submitSubCategory(e, cat.id)} className="flex items-end gap-3 mb-4 bg-brand-50 rounded-md p-3">
                <div className="flex-1">
                  <Input label={editingSub ? "Edit Sub-category Name" : "Sub-category Name"} required value={subName} onChange={(e) => setSubName(e.target.value)} autoFocus />
                </div>
                <Button type="submit" disabled={subBusy}>{subBusy ? "Saving…" : editingSub ? "Save Changes" : "Save"}</Button>
                <Button type="button" variant="ghost" onClick={() => { setSubFormForCategory(null); setEditingSub(null); setSubName(""); setSubError(""); }}>Cancel</Button>
              </form>
            )}
            {subError && subFormForCategory === cat.id && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{subError}</div>}

            {(subCategoriesByCategory[cat.id] || []).length === 0 ? (
              <p className="text-xs text-ink/40">No sub-categories.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(subCategoriesByCategory[cat.id] || []).map((s) => (
                  <button
                    type="button" key={s.id} onClick={() => openEditSub(cat.id, s)}
                    className="text-xs bg-ink/5 text-ink/70 rounded-md px-2.5 py-1.5 hover:bg-brand-50 hover:text-brand-700 inline-flex items-center gap-1"
                    title="Click to edit"
                  >
                    {s.name} <Pencil size={11} className="opacity-50" />
                  </button>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
