import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import client, { apiErrorMessage } from "../api/client";
import { useMasters } from "../hooks/useMasters";
import { useAuth } from "../context/AuthContext";
import { Card, Table, StatusBadge, Button, Input, Select, formatMoney, formatDate } from "../components/ui";
import DateRangePicker, { defaultMonthRange } from "../components/DateRangePicker";
import Attachments from "../components/Attachments";
import SubCategorySelect from "../components/SubCategorySelect";
import { Plus, X, Trash2, Pencil, FileDown, Mail, CheckCircle2, ChevronLeft, ChevronRight, Columns3 } from "lucide-react";

const CLAIM_STATUSES = ["DRAFT", "SUBMITTED", "PENDING_ACCOUNTS_APPROVAL", "APPROVED", "REJECTED"];
const PAGE_SIZES = [25, 50, 100];

// Columns the user can show/hide via the "Columns" picker. claim_number
// stays mandatory - excluded here so it's always rendered regardless of
// what's hidden.
const TOGGLEABLE_COLUMNS = [
  { key: "employee_id", label: "Employee" },
  { key: "category_id", label: "Overall Head" },
  { key: "description", label: "Description" },
  { key: "claim_date", label: "Date" },
  { key: "total_amount", label: "Amount" },
  { key: "status", label: "Status" },
];
const HIDDEN_COLUMNS_STORAGE_KEY = "expms_claims_hidden_columns";

function ColumnsPicker({ hidden, onToggle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <Button variant="outline" onClick={() => setOpen((o) => !o)}>
        <Columns3 size={16} /> Columns
      </Button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-64 max-h-80 overflow-y-auto bg-white border border-ink/15 rounded-md shadow-lg py-2">
          {TOGGLEABLE_COLUMNS.map((c) => (
            <label key={c.key} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-brand-50 cursor-pointer">
              <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => onToggle(c.key)} />
              {c.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function ClaimsList({ mineOnly = false, approvalsOnly = false }) {
  const { user } = useAuth();
  const masters = useMasters();
  const [claims, setClaims] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [bounds, setBounds] = useState(null);
  // Claim Approvals has no date filter UI (see below) and must never
  // silently hide an older pending approval, so only the plain claims list
  // defaults to "this month" - approvalsOnly keeps the unbounded default.
  const [range, setRange] = useState(approvalsOnly ? { from: "", to: "" } : defaultMonthRange);
  const [projectId, setProjectId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [claimStatus, setClaimStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState(null);
  const [hiddenCols, setHiddenCols] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE_KEY) || "[]")); } catch { return new Set(); }
  });
  const [exporting, setExporting] = useState(false);
  const navigate = useNavigate();

  function toggleColumn(key) {
    setHiddenCols((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key); else next.add(key);
      localStorage.setItem(HIDDEN_COLUMNS_STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => setBounds(res.data)).catch(() => {});
  }, []);

  function filterParams() {
    const params = {};
    if (mineOnly) params.mine = true;
    if (approvalsOnly) params.pending_for_me = true;
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    if (projectId) params.project_id = projectId;
    if (categoryId) params.category_id = categoryId;
    if (claimStatus) params.status_ = claimStatus;
    return params;
  }

  function load() {
    const listParams = { ...filterParams(), page, page_size: pageSize };
    if (sort) { listParams.sort_by = sort.key; listParams.sort_dir = sort.dir; }
    client.get("/claims", { params: listParams }).then((res) => setClaims(res.data));
    client.get("/claims/summary", { params: filterParams() }).then((res) => setSummary(res.data));
  }
  useEffect(load, [mineOnly, approvalsOnly, range.from, range.to, projectId, categoryId, claimStatus, page, pageSize, sort]);
  useEffect(() => { setPage(1); }, [mineOnly, approvalsOnly, range.from, range.to, projectId, categoryId, claimStatus, pageSize, sort]);

  async function downloadPdf() {
    const visibleColumns = TOGGLEABLE_COLUMNS.map((c) => c.key).filter((k) => !hiddenCols.has(k));
    setExporting(true);
    try {
      const res = await client.get("/claims/export-pdf", {
        params: { ...filterParams(), columns: visibleColumns.join(",") },
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `claims-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  const totalPages = summary ? Math.max(1, Math.ceil(summary.count / pageSize)) : 1;

  const empName = (id) => masters.employees.find((e) => e.id === id)?.employee_name || id;
  const categoryName = (id) => masters.categories.find((c) => c.id === id)?.name || "—";
  const canCreate = mineOnly || ["ADMIN", "SUPER_ADMIN"].includes(user?.role);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">{approvalsOnly ? "Claim Approvals" : mineOnly ? "My Claims" : "Employee Claims"}</h1>
          <p className="text-sm text-ink/50 mt-0.5">
            {approvalsOnly ? "Claims awaiting your review (yours to approve at their current stage)." : "Multi-line expense claims from draft through payment."}
          </p>
        </div>
        {canCreate && !approvalsOnly && <Button onClick={() => setShowForm(true)}><Plus size={16} /> New Claim</Button>}
      </div>

      {showForm && (
        <ClaimForm
          masters={masters} defaultEmployeeId={user?.employee_id}
          onClose={() => setShowForm(false)} onCreated={() => { setShowForm(false); load(); }}
        />
      )}

      {!approvalsOnly && (
        <Card>
          <div className="flex flex-wrap items-end gap-4">
            <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
          </div>
          <div className="flex flex-wrap items-end gap-4 mt-4 pt-4 border-t border-ink/10">
            <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-44">
              <option value="">All Projects</option>
              {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Select label="Overall Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-44">
              <option value="">All Heads</option>
              {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Status" value={claimStatus} onChange={(e) => setClaimStatus(e.target.value)} className="w-44">
              <option value="">All Statuses</option>
              {CLAIM_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
        </Card>
      )}

      <Card>
        <div className="flex justify-end gap-2 mb-2">
          <Button variant="outline" onClick={downloadPdf} disabled={exporting}>
            <FileDown size={16} /> {exporting ? "Preparing…" : "Download PDF"}
          </Button>
          <ColumnsPicker hidden={hiddenCols} onToggle={toggleColumn} />
        </div>
        <Table
          compact
          stickyHeader
          sort={sort}
          onSortChange={setSort}
          columns={[
            { key: "claim_number", header: "Claim #", sortable: true },
            { key: "employee_id", header: "Employee", sortable: true, render: (r) => empName(r.employee_id) },
            { key: "category_id", header: "Overall Head", sortable: true, render: (r) => categoryName(r.category_id) },
            {
              key: "description", header: "Description",
              render: (r) => <span className="block min-w-[260px] max-w-[420px] whitespace-normal break-words text-ink/60">{r.description || "—"}</span>,
            },
            { key: "claim_date", header: "Date", sortable: true, render: (r) => formatDate(r.claim_date) },
            { key: "total_amount", header: "Amount", sortable: true, render: (r) => <span className="tabular">{formatMoney(r.total_amount)}</span> },
            { key: "status", header: "Status", sortable: true, render: (r) => <StatusBadge status={r.status} /> },
          ].filter((c) => c.key === "claim_number" || !hiddenCols.has(c.key))}
          rows={claims}
          onRowClick={(r) => navigate(`/claims/${r.id}`)}
          footer={summary && {
            claim_number: `${summary.count} claim(s)`,
            total_amount: <span className="tabular">{formatMoney(summary.total_amount)}</span>,
          }}
        />

        {summary && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-ink/10 text-sm text-ink/60">
            <div className="flex items-center gap-2">
              <span>Rows per page</span>
              <div className="w-20">
                <Select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                  {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span>Page {page} of {totalPages} · {summary.count} total</span>
              <div className="flex gap-1">
                <button
                  type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="p-1.5 rounded-md border border-ink/15 disabled:opacity-30 hover:bg-brand-50"
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  type="button" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1.5 rounded-md border border-ink/15 disabled:opacity-30 hover:bg-brand-50"
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

export function ClaimDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const masters = useMasters();
  const [claim, setClaim] = useState(null);
  const [error, setError] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailError, setEmailError] = useState("");
  const [emailSentTo, setEmailSentTo] = useState("");
  const navigate = useNavigate();

  function load() { client.get(`/claims/${id}`).then((res) => setClaim(res.data)); }
  useEffect(load, [id]);

  if (!claim) return <div className="text-sm text-ink/40">Loading…</div>;

  const empName = masters.employees.find((e) => e.id === claim.employee_id)?.employee_name || claim.employee_id;
  const categoryName = masters.categories.find((c) => c.id === claim.category_id)?.name || "—";
  const isOwner = user?.employee_id === claim.employee_id;
  const canEdit = (isOwner || ["ADMIN", "SUPER_ADMIN"].includes(user?.role)) && ["DRAFT", "REJECTED"].includes(claim.status);
  const isPrivileged = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const canApprove =
    isPrivileged ||
    (user?.role === "MANAGER" && claim.status === "SUBMITTED") ||
    (user?.role === "ACCOUNTS" && claim.status === "PENDING_ACCOUNTS_APPROVAL");
  const canAct = canApprove && ["SUBMITTED", "PENDING_ACCOUNTS_APPROVAL"].includes(claim.status);
  const stageLabel = claim.status === "SUBMITTED"
    ? "Awaiting the employee's manager"
    : claim.status === "PENDING_ACCOUNTS_APPROVAL"
    ? "Awaiting the project's Accounts approver"
    : null;

  async function act(action, payload) {
    setError("");
    try {
      await client.post(`/claims/${id}/${action}`, payload);
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function deleteClaim() {
    if (!window.confirm(`Delete claim ${claim.claim_number}? This cannot be undone.`)) return;
    setError("");
    try {
      await client.delete(`/claims/${id}`);
      navigate("/claims");
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function downloadPdf() {
    setDownloadingPdf(true);
    setError("");
    try {
      const res = await client.get(`/claims/${id}/download-pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${claim.claim_number}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
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
      setDownloadingPdf(false);
    }
  }

  async function sendEmail(e) {
    e.preventDefault();
    setEmailBusy(true);
    setEmailError("");
    setEmailSentTo("");
    try {
      await client.post(`/claims/${id}/email-pdf`, { email: emailTo });
      setEmailSentTo(emailTo);
      setShowEmailForm(false);
      setEmailTo("");
    } catch (err) {
      setEmailError(apiErrorMessage(err));
    } finally {
      setEmailBusy(false);
    }
  }

  return (
    <div className="space-y-6 w-full">
      <Link to="/claims" className="text-sm text-brand-600 hover:underline">← Back to claims</Link>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold">{claim.claim_number}</h1>
          <p className="text-sm text-ink/50 mt-0.5">{empName} · {formatDate(claim.claim_date)} · {categoryName}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button type="button" variant="outline" onClick={downloadPdf} disabled={downloadingPdf}>
            <FileDown size={15} /> {downloadingPdf ? "Preparing…" : "Download PDF"}
          </Button>
          <Button type="button" variant="outline" onClick={() => { setShowEmailForm((s) => !s); setEmailError(""); }}>
            <Mail size={15} /> Send Email
          </Button>
          <StatusBadge status={claim.status} />
        </div>
      </div>

      {showEmailForm && (
        <Card className="max-w-md">
          <form onSubmit={sendEmail} className="flex items-end gap-3">
            <div className="flex-1">
              <Input label="Send PDF to email address" type="email" required value={emailTo}
                onChange={(e) => setEmailTo(e.target.value)} placeholder="name@example.com" autoFocus />
            </div>
            <Button type="submit" disabled={emailBusy}>{emailBusy ? "Sending…" : "Send"}</Button>
            <Button type="button" variant="ghost" onClick={() => { setShowEmailForm(false); setEmailError(""); }}>Cancel</Button>
          </form>
          {emailError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mt-3">{emailError}</div>}
        </Card>
      )}
      {emailSentTo && !showEmailForm && (
        <div className="text-sm text-ok bg-ok/10 rounded-md px-3 py-2 inline-flex items-center gap-1.5">
          <CheckCircle2 size={14} /> Emailed to {emailSentTo}
        </div>
      )}

      {stageLabel && (
        <div className="text-xs text-ink/50 bg-ink/5 rounded-md px-3 py-2 inline-block">{stageLabel}</div>
      )}

      {claim.expense_number && (
        <div className="text-xs text-ok bg-ok/10 rounded-md px-3 py-2 inline-block">
          Recorded as a single expense: <span className="font-semibold tabular">{claim.expense_number}</span> — ready for payment.
        </div>
      )}

      {claim.description && (
        <Card>
          <div className="text-xs font-medium text-ink/40 mb-1">Description</div>
          <div className="text-sm text-ink/70">{claim.description}</div>
        </Card>
      )}

      <div className="flex justify-end">
        <Attachments documentType="CLAIM" claimId={claim.id} label="Overall Claim Attachments" readOnly={!canEdit} />
      </div>

      {showEdit ? (
        <ClaimForm
          masters={masters} defaultEmployeeId={claim.employee_id} editingClaim={claim}
          onClose={() => setShowEdit(false)} onCreated={() => { setShowEdit(false); load(); }}
        />
      ) : (
      <Card>
        <Table
          columns={[
            { key: "expense_date", header: "Date", render: (r) => formatDate(r.expense_date) },
            { key: "expense_head_id", header: "Head", render: (r) => masters.categories.find((c) => c.id === r.expense_head_id)?.name || "—" },
            { key: "expense_sub_head_id", header: "Sub-Head", render: (r) => masters.subCategories.find((s) => s.id === r.expense_sub_head_id)?.name || "—" },
            {
              key: "description", header: "Description",
              render: (r) => <span className="block min-w-[280px] max-w-[520px] whitespace-normal break-words">{r.description || "—"}</span>,
            },
            { key: "amount", header: "Amount", render: (r) => <span className="tabular">{formatMoney(r.amount)}</span> },
            {
              key: "proof", header: "Proof",
              render: (r) => <Attachments documentType="CLAIM_LINE" claimLineId={r.id} compact label="Screenshot / Proof" readOnly={!canEdit} />,
            },
          ]}
          rows={claim.lines}
        />
        <div className="text-right mt-3 pt-3 border-t border-ink/10 text-sm">
          Total: <span className="tabular font-semibold text-lg ml-1">{formatMoney(claim.total_amount)}</span>
        </div>
      </Card>
      )}

      {claim.status === "REJECTED" && claim.rejection_reason && (
        <Card className="border-danger/30 bg-danger/5">
          <div className="text-sm font-medium text-danger mb-1">Rejection reason</div>
          <div className="text-sm text-ink/70">{claim.rejection_reason}</div>
        </Card>
      )}

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <div className="flex gap-2 flex-wrap">
        {canEdit && !showEdit && (
          <>
            <Button onClick={() => act("submit")}>Submit Claim</Button>
            <Button variant="outline" onClick={() => setShowEdit(true)}>Edit Claim</Button>
            <Button variant="danger" onClick={deleteClaim}>Delete Claim</Button>
          </>
        )}
        {canAct && (
          <>
            <Button variant="accent" onClick={() => act("approve")}>Approve</Button>
            <Button variant="danger" onClick={() => setShowReject(true)}>Reject</Button>
          </>
        )}
      </div>

      {showReject && (
        <Card className="max-w-md">
          <h3 className="font-medium mb-2">Reject claim</h3>
          <Input label="Reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
          <div className="flex gap-2 mt-3">
            <Button variant="danger" onClick={() => { act("reject", { reason: rejectReason }); setShowReject(false); }}>Confirm Reject</Button>
            <Button variant="ghost" onClick={() => setShowReject(false)}>Cancel</Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function ClaimForm({ masters, defaultEmployeeId, editingClaim, onClose, onCreated }) {
  const [employeeId, setEmployeeId] = useState(editingClaim?.employee_id || defaultEmployeeId || "");
  const [projectId, setProjectId] = useState(editingClaim?.project_id || "");
  const [categoryId, setCategoryId] = useState(editingClaim?.category_id || "");
  const [description, setDescription] = useState(editingClaim?.description || "");
  const [lines, setLines] = useState(
    editingClaim?.lines?.length
      ? [...editingClaim.lines]
          .sort((a, b) => a.expense_date.localeCompare(b.expense_date))
          .map((l) => ({
            id: l.id, expense_date: l.expense_date, expense_head_id: l.expense_head_id,
            expense_sub_head_id: l.expense_sub_head_id || "", description: l.description || "", amount: l.amount,
            // Already-saved lines start locked - editing one requires an
            // explicit click on its Edit icon, so the rest of an already-
            // saved claim can never be touched by accident while adding or
            // removing an unrelated line.
            locked: true,
          }))
      : [{ expense_date: new Date().toISOString().slice(0, 10), expense_head_id: "", expense_sub_head_id: "", description: "", amount: "" }]
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateLine(i, k, v) {
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, [k]: v } : l)));
  }
  function unlockLine(i) {
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, locked: false } : l)));
  }
  function addLine() {
    setLines((ls) => [...ls, { expense_date: new Date().toISOString().slice(0, 10), expense_head_id: "", expense_sub_head_id: "", description: "", amount: "" }]);
  }
  function removeLine(i) {
    setLines((ls) => ls.filter((_, idx) => idx !== i));
  }

  const total = lines.reduce((s, l) => s + Number(l.amount || 0), 0);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        employee_id: Number(employeeId),
        project_id: projectId || null,
        category_id: Number(categoryId),
        description,
        lines: lines.map(({ locked, ...l }) => ({ ...l, expense_head_id: Number(l.expense_head_id), expense_sub_head_id: l.expense_sub_head_id || null, amount: Number(l.amount) })),
      };
      if (editingClaim) {
        await client.put(`/claims/${editingClaim.id}`, body);
      } else {
        await client.post("/claims", body);
      }
      onCreated();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const selectedEmployee = masters.employees.find((emp) => emp.id === Number(employeeId));
  const allowedProjects = selectedEmployee?.project_ids?.length
    ? masters.projects.filter((p) => selectedEmployee.project_ids.includes(p.id))
    : masters.projects;

  return (
    <Card className="relative">
      <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
      <h2 className="font-display font-semibold text-lg mb-4">{editingClaim ? `Edit Claim ${editingClaim.claim_number}` : "New Employee Claim"}</h2>
      <form onSubmit={submit} className="space-y-4 w-full">
        <div className="grid grid-cols-2 gap-4">
          <Select label="Employee" value={employeeId} onChange={(e) => { setEmployeeId(e.target.value); setProjectId(""); }} required disabled={!!defaultEmployeeId || !!editingClaim}>
            <option value="">Select…</option>
            {masters.employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.employee_name}</option>)}
          </Select>
          <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">— none —</option>
            {allowedProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select label="Overall Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} required>
            <option value="">Select…</option>
            {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />

        <div className="space-y-2">
          <div className="text-xs font-medium text-ink/60">Expense Lines (under {masters.categories.find((c) => c.id === Number(categoryId))?.name || "the Overall Head above"})</div>
          {lines.map((l, i) => l.locked ? (
            <div key={l.id ?? i} className="grid grid-cols-12 gap-2 items-center bg-ink/5 rounded-md p-3 text-sm">
              <div className="col-span-2 text-ink/70">{formatDate(l.expense_date)}</div>
              <div className="col-span-2 text-ink/70">{masters.categories.find((c) => c.id === Number(l.expense_head_id))?.name || "—"}</div>
              <div className="col-span-2 text-ink/70">{masters.subCategories.find((s) => s.id === Number(l.expense_sub_head_id))?.name || "—"}</div>
              <div className="col-span-3 text-ink/70 truncate">{l.description || "—"}</div>
              <div className="col-span-2 tabular font-medium">{formatMoney(l.amount)}</div>
              <div className="col-span-1 flex items-center gap-2 justify-end">
                <button type="button" onClick={() => unlockLine(i)} className="text-ink/30 hover:text-brand-700" title="Edit this item">
                  <Pencil size={15} />
                </button>
                {lines.length > 1 && <button type="button" onClick={() => removeLine(i)} className="text-ink/30 hover:text-danger" title="Delete this item"><Trash2 size={16} /></button>}
              </div>
            </div>
          ) : (
            <div key={l.id ?? i} className="grid grid-cols-12 gap-2 items-end bg-brand-50 rounded-md p-3">
              <div className="col-span-2">
                <Input label="Date" type="date" value={l.expense_date} onChange={(e) => updateLine(i, "expense_date", e.target.value)} required />
              </div>
              <div className="col-span-2">
                <Select label="Head" value={l.expense_head_id} onChange={(e) => { updateLine(i, "expense_head_id", e.target.value); updateLine(i, "expense_sub_head_id", ""); }} required>
                  <option value="">Select…</option>
                  {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              </div>
              <div className="col-span-2">
                <SubCategorySelect label="Sub-Head" categoryId={l.expense_head_id} value={l.expense_sub_head_id} onChange={(v) => updateLine(i, "expense_sub_head_id", v)} />
              </div>
              <div className="col-span-3">
                <Input label="Description" value={l.description} onChange={(e) => updateLine(i, "description", e.target.value)} />
              </div>
              <div className="col-span-2">
                <Input label="Amount" type="number" step="0.01" value={l.amount} onChange={(e) => updateLine(i, "amount", e.target.value)} required />
              </div>
              <div className="col-span-1 pb-1">
                {lines.length > 1 && <button type="button" onClick={() => removeLine(i)} className="text-ink/30 hover:text-danger" title="Delete this item"><Trash2 size={16} /></button>}
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" onClick={addLine}><Plus size={14} /> Add Expense</Button>
        </div>

        <div className="text-sm text-right text-ink/60">Claim Total: <span className="tabular font-semibold text-lg text-ink">{formatMoney(total)}</span></div>

        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : editingClaim ? "Save Changes" : "Save Draft"}</Button>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
