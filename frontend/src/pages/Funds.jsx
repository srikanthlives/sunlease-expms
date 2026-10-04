import { useEffect, useState, useCallback } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Table, StatCard, Button, Input, Textarea, Select, formatMoney, formatDate } from "../components/ui";
import { Plus, X, Pencil, Ban } from "lucide-react";

const TABS = [
  { key: "sheet", label: "Balance Sheet" },
  { key: "transfers", label: "Transfers & Funding" },
  { key: "accounts", label: "Accounts" },
  { key: "entities", label: "Funding Entities" },
];
const ACCOUNT_TYPES = ["BANK", "CASH", "UPI", "PETTY_CASH"];
const today = () => new Date().toISOString().slice(0, 10);

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
        <h2 className="font-display font-semibold text-lg mb-4">{title}</h2>
        {children}
      </div>
    </div>
  );
}

const money = (v) => <span className="tabular">{formatMoney(v)}</span>;

function BalanceSheet() {
  const [asOf, setAsOf] = useState(today());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/funds/balance-sheet", { params: { as_of: asOf } })
      .then((r) => setData(r.data)).catch((e) => setError(apiErrorMessage(e)));
  }, [asOf]);

  if (error) return <div className="text-sm text-danger">{error}</div>;
  if (!data) return <div className="text-sm text-ink/40">Loading…</div>;
  const t = data.totals;
  const cols = [
    { key: "account_name", label: "Account" },
    { key: "opening_balance", label: "Opening", render: (r) => money(r.opening_balance) },
    { key: "funded", label: "Funded", render: (r) => money(r.funded) },
    { key: "transfers_in", label: "Transfers In", render: (r) => money(r.transfers_in) },
    { key: "receipts", label: "Receipts", render: (r) => money(r.receipts) },
    { key: "transfers_out", label: "Transfers Out", render: (r) => money(r.transfers_out) },
    { key: "payments", label: "Payments", render: (r) => money(r.payments) },
    { key: "balance", label: "Balance", render: (r) => <span className="tabular font-semibold">{formatMoney(r.balance)}</span> },
  ];
  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div className="w-44"><Input label="As of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Funded" value={formatMoney(t.total_funded)} />
        <StatCard label="Total Payments Out" value={formatMoney(t.payments)} />
        <StatCard label="Receipts In" value={formatMoney(t.receipts)} />
        <StatCard label="Net Balance (all accounts)" value={formatMoney(t.balance)} />
      </div>
      {data.groups.map((g) => (
        <Card key={g.entity_id ?? "none"} className="p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
            <h3 className="font-display font-semibold">{g.entity_name}</h3>
            <div className="text-sm text-ink/60">
              Funded: <span className="tabular font-semibold text-ink">{formatMoney(g.total_funded)}</span>
              <span className="mx-2">·</span>
              Balance held: <span className="tabular font-semibold text-ink">{formatMoney(g.balance)}</span>
            </div>
          </div>
          <Table columns={cols} rows={g.accounts} compact empty="No accounts under this entity."
            footer={g.accounts.length > 1 ? {
              account_name: "Total",
              ...Object.fromEntries(["opening_balance", "funded", "transfers_in", "receipts", "transfers_out", "payments", "balance"].map((k) => [k, money(g[k])])),
            } : undefined} />
        </Card>
      ))}
    </div>
  );
}

function TransferForm({ accounts, entities, onSaved, onClose }) {
  const [f, setF] = useState({ kind: "TRANSFER", transfer_date: today(), from_account_id: "", to_account_id: "", funding_entity_id: "", amount: "", reference_number: "", remarks: "" });
  const [err, setErr] = useState("");
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      await client.post("/funds/transfers", {
        kind: f.kind, transfer_date: f.transfer_date, amount: f.amount,
        from_account_id: f.kind === "TRANSFER" ? Number(f.from_account_id) || null : null,
        to_account_id: Number(f.to_account_id),
        funding_entity_id: f.kind === "FUNDING" && f.funding_entity_id ? Number(f.funding_entity_id) : null,
        reference_number: f.reference_number || null, remarks: f.remarks || null,
      });
      onSaved();
    } catch (e2) { setErr(apiErrorMessage(e2)); }
  }
  const opts = (list) => list.filter((a) => a.is_active).map((a) => <option key={a.id} value={a.id}>{a.account_name}</option>);
  return (
    <form onSubmit={submit} className="space-y-4">
      <Select label="Type" value={f.kind} onChange={(e) => set("kind", e.target.value)}>
        <option value="TRANSFER">Transfer between accounts</option>
        <option value="FUNDING">Funding received from entity</option>
      </Select>
      {f.kind === "TRANSFER" ? (
        <Select label="From Account" value={f.from_account_id} onChange={(e) => set("from_account_id", e.target.value)} required>
          <option value="">Select…</option>{opts(accounts)}
        </Select>
      ) : (
        <Select label="Funding Entity (defaults to account's entity)" value={f.funding_entity_id} onChange={(e) => set("funding_entity_id", e.target.value)}>
          <option value="">Account's entity</option>
          {entities.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </Select>
      )}
      <Select label="To Account" value={f.to_account_id} onChange={(e) => set("to_account_id", e.target.value)} required>
        <option value="">Select…</option>{opts(accounts)}
      </Select>
      <div className="grid grid-cols-2 gap-4">
        <Input label="Date" type="date" value={f.transfer_date} onChange={(e) => set("transfer_date", e.target.value)} required />
        <Input label="Amount" type="number" step="0.01" min="0" value={f.amount} onChange={(e) => set("amount", e.target.value)} required />
      </div>
      <Input label="Reference No." value={f.reference_number} onChange={(e) => set("reference_number", e.target.value)} />
      <Textarea label="Remarks" value={f.remarks} onChange={(e) => set("remarks", e.target.value)} />
      {err && <div className="text-sm text-danger">{err}</div>}
      <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit">Save</Button></div>
    </form>
  );
}

function Transfers({ accounts, entities }) {
  const [rows, setRows] = useState([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    client.get("/funds/transfers").then((r) => setRows(r.data)).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  async function cancel(t) {
    const reason = window.prompt(`Cancel ${t.transfer_number}? Enter a reason:`);
    if (!reason) return;
    try { await client.post(`/funds/transfers/${t.id}/cancel`, { reason }); load(); } catch (e) { setError(apiErrorMessage(e)); }
  }
  const cols = [
    { key: "transfer_number", label: "No." },
    { key: "transfer_date", label: "Date", render: (r) => formatDate(r.transfer_date) },
    { key: "kind", label: "Type", render: (r) => (r.kind === "FUNDING" ? "Funding" : "Transfer") },
    { key: "from_account_name", label: "From", render: (r) => r.kind === "FUNDING" ? (r.funding_entity_name || "—") : r.from_account_name },
    { key: "to_account_name", label: "To" },
    { key: "amount", label: "Amount", render: (r) => <span className={`tabular ${r.is_cancelled ? "line-through text-ink/40" : ""}`}>{formatMoney(r.amount)}</span> },
    { key: "reference_number", label: "Ref" },
    { key: "remarks", label: "Remarks", render: (r) => r.is_cancelled ? <span className="text-danger">Cancelled: {r.cancel_reason}</span> : r.remarks },
    { key: "_a", label: "", render: (r) => !r.is_cancelled && <button title="Cancel" onClick={() => cancel(r)} className="text-ink/40 hover:text-danger"><Ban size={15} /></button> },
  ];
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setAdding(true)}><Plus size={15} className="mr-1 inline" />New Transfer / Funding</Button></div>
      {error && <div className="text-sm text-danger">{error}</div>}
      <Card><Table columns={cols} rows={rows} compact empty="No transfers yet." /></Card>
      {adding && (
        <Modal title="New Transfer / Funding" onClose={() => setAdding(false)}>
          <TransferForm accounts={accounts} entities={entities} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); load(); }} />
        </Modal>
      )}
    </div>
  );
}

function Accounts({ accounts, entities, reload }) {
  const [editing, setEditing] = useState(null); // {} for new
  const [f, setF] = useState({});
  const [err, setErr] = useState("");
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  function open(a) {
    setErr("");
    setF(a ? { ...a, funding_entity_id: a.funding_entity_id ?? "" } : { account_name: "", account_type: "BANK", account_number: "", bank_name: "", ifsc: "", funding_entity_id: "", opening_balance: 0, is_active: true });
    setEditing(a || {});
  }
  async function submit(e) {
    e.preventDefault();
    const body = {
      account_name: f.account_name, account_type: f.account_type, account_number: f.account_number || null,
      bank_name: f.bank_name || null, ifsc: f.ifsc || null, is_active: f.is_active,
      funding_entity_id: f.funding_entity_id ? Number(f.funding_entity_id) : null,
      opening_balance: f.opening_balance || 0,
    };
    try {
      if (editing.id) await client.put(`/funds/accounts/${editing.id}`, body);
      else await client.post("/funds/accounts", body);
      setEditing(null); reload();
    } catch (e2) { setErr(apiErrorMessage(e2)); }
  }
  const cols = [
    { key: "account_name", label: "Account" },
    { key: "account_type", label: "Type" },
    { key: "funding_entity_name", label: "Funding Entity", render: (r) => r.funding_entity_name || "—" },
    { key: "opening_balance", label: "Opening Balance", render: (r) => money(r.opening_balance) },
    { key: "is_active", label: "Status", render: (r) => (r.is_active ? "Active" : "Inactive") },
    { key: "_a", label: "", render: (r) => <button onClick={() => open(r)} className="text-ink/40 hover:text-ink"><Pencil size={15} /></button> },
  ];
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => open(null)}><Plus size={15} className="mr-1 inline" />New Account</Button></div>
      <Card><Table columns={cols} rows={accounts} compact empty="No accounts." /></Card>
      {editing && (
        <Modal title={editing.id ? "Edit Account" : "New Account"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-4">
            <Input label="Account Name" value={f.account_name} onChange={(e) => set("account_name", e.target.value)} required />
            <div className="grid grid-cols-2 gap-4">
              <Select label="Type" value={f.account_type} onChange={(e) => set("account_type", e.target.value)}>
                {ACCOUNT_TYPES.map((t) => <option key={t}>{t}</option>)}
              </Select>
              <Select label="Funding Entity" value={f.funding_entity_id} onChange={(e) => set("funding_entity_id", e.target.value)}>
                <option value="">None</option>
                {entities.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Account Number" value={f.account_number || ""} onChange={(e) => set("account_number", e.target.value)} />
              <Input label="Bank Name" value={f.bank_name || ""} onChange={(e) => set("bank_name", e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="IFSC" value={f.ifsc || ""} onChange={(e) => set("ifsc", e.target.value)} />
              <Input label="Opening Balance" type="number" step="0.01" value={f.opening_balance} onChange={(e) => set("opening_balance", e.target.value)} />
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f.is_active} onChange={(e) => set("is_active", e.target.checked)} />Active</label>
            {err && <div className="text-sm text-danger">{err}</div>}
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit">Save</Button></div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function Entities({ entities, reload }) {
  const [editing, setEditing] = useState(null);
  const [f, setF] = useState({});
  const [err, setErr] = useState("");
  function open(e) { setErr(""); setF(e ? { ...e, notes: e.notes || "" } : { name: "", notes: "", is_active: true }); setEditing(e || {}); }
  async function submit(e) {
    e.preventDefault();
    const body = { name: f.name, notes: f.notes || null, is_active: f.is_active };
    try {
      if (editing.id) await client.put(`/funds/entities/${editing.id}`, body);
      else await client.post("/funds/entities", body);
      setEditing(null); reload();
    } catch (e2) { setErr(apiErrorMessage(e2)); }
  }
  const cols = [
    { key: "name", label: "Entity" },
    { key: "account_count", label: "Accounts" },
    { key: "notes", label: "Notes" },
    { key: "is_active", label: "Status", render: (r) => (r.is_active ? "Active" : "Inactive") },
    { key: "_a", label: "", render: (r) => <button onClick={() => open(r)} className="text-ink/40 hover:text-ink"><Pencil size={15} /></button> },
  ];
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => open(null)}><Plus size={15} className="mr-1 inline" />New Funding Entity</Button></div>
      <Card><Table columns={cols} rows={entities} compact empty="No funding entities yet." /></Card>
      {editing && (
        <Modal title={editing.id ? "Edit Funding Entity" : "New Funding Entity"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-4">
            <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
            <Textarea label="Notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />Active</label>
            {err && <div className="text-sm text-danger">{err}</div>}
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit">Save</Button></div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export default function Funds() {
  const [tab, setTab] = useState("sheet");
  const [accounts, setAccounts] = useState([]);
  const [entities, setEntities] = useState([]);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => {
    client.get("/funds/accounts").then((r) => setAccounts(r.data));
    client.get("/funds/entities").then((r) => setEntities(r.data));
    setVersion((v) => v + 1);
  }, []);
  useEffect(reload, [reload]);

  return (
    <div className="space-y-5">
      <h1 className="font-display font-semibold text-xl">Funds</h1>
      <div className="flex gap-1 border-b border-ink/10">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === t.key ? "border-brand-500 text-ink" : "border-transparent text-ink/50 hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "sheet" && <BalanceSheet key={version} />}
      {tab === "transfers" && <Transfers accounts={accounts} entities={entities} />}
      {tab === "accounts" && <Accounts accounts={accounts} entities={entities} reload={reload} />}
      {tab === "entities" && <Entities entities={entities} reload={reload} />}
    </div>
  );
}
