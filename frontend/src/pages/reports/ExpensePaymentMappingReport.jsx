import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { useMasters } from "../../hooks/useMasters";
import { Card, Select, StatusBadge, formatMoney, formatDate } from "../../components/ui";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import { ArrowLeft, ChevronDown, ChevronRight, ChevronsDown, ChevronsUp, Wallet, Split } from "lucide-react";

const SOURCE_TYPES = ["EXPENSE", "INVOICE", "EMPLOYEE_CLAIM"];
const PAYMENT_STATUSES = ["UNPAID", "PARTIALLY_PAID", "PAID"];

function ExpenseRow({ row, expanded, onToggle }) {
  const hasPayments = row.payments.length > 0;
  return (
    <div className="border-b border-ink/10 last:border-0">
      <button
        type="button"
        onClick={() => hasPayments && onToggle(row.expense_id)}
        className={`w-full flex items-center gap-3 px-3 py-3 text-left ${hasPayments ? "hover:bg-brand-50 cursor-pointer" : "cursor-default"}`}
      >
        <span className="w-4 shrink-0 text-ink/30">
          {hasPayments ? (expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : null}
        </span>
        <span className="w-32 shrink-0 font-medium text-sm">{row.expense_number}</span>
        <span className="w-24 shrink-0 text-xs text-ink/50 whitespace-nowrap">{formatDate(row.expense_date)}</span>
        <span className="w-32 shrink-0 text-[11px] text-ink/40 uppercase whitespace-nowrap overflow-hidden text-ellipsis" title={row.source_type.replace(/_/g, " ")}>
          {row.source_type.replace(/_/g, " ")}
        </span>
        <span className="flex-1 min-w-0 truncate text-sm" title={row.payee}>{row.payee}</span>
        <span className="w-40 shrink-0 truncate text-xs text-ink/50" title={`${row.category_name}${row.sub_category_name ? " / " + row.sub_category_name : ""}`}>
          {row.category_name}{row.sub_category_name ? ` / ${row.sub_category_name}` : ""}
        </span>
        <span className="w-28 shrink-0 text-right tabular text-sm">{formatMoney(row.total_amount)}</span>
        <span className="w-28 shrink-0 text-right tabular text-sm text-ok">{formatMoney(row.paid_amount)}</span>
        <span className="w-28 shrink-0 text-right tabular text-sm text-warn">{formatMoney(row.balance_due)}</span>
        <span className="w-32 shrink-0 flex justify-end"><StatusBadge status={row.payment_status} /></span>
      </button>

      {expanded && hasPayments && (
        <div className="pb-2 pl-11 pr-3 space-y-1.5">
          {row.payments.map((p) => (
            <div key={p.payment_id} className="flex items-start gap-3 bg-ink/[0.03] rounded-md px-3 py-2 text-xs">
              <Wallet size={13} className="shrink-0 mt-0.5 text-ink/30" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-ink/80">{p.payment_number}</span>
                  <span className="text-ink/40">{formatDate(p.payment_date)}</span>
                  <span className="text-ink/40">· {p.account_name} · {p.payment_mode}</span>
                  {p.reference_number && <span className="text-ink/40">· Ref {p.reference_number}</span>}
                  {p.covers_multiple_expenses && (
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-warn/40 bg-warn/10 text-warn font-medium"
                      title={`This payment also covers: ${p.other_expense_numbers.join(", ")}`}
                    >
                      <Split size={11} /> Split payment · covers {p.expenses_covered_count} expenses
                    </span>
                  )}
                </div>
                {p.covers_multiple_expenses && p.other_expense_numbers.length > 0 && (
                  <div className="text-ink/40 mt-0.5">Also paid: {p.other_expense_numbers.join(", ")}</div>
                )}
              </div>
              <div className="shrink-0 text-right">
                <div className="tabular font-medium">{formatMoney(p.allocated_amount)}</div>
                {p.covers_multiple_expenses && (
                  <div className="text-ink/40 tabular">of {formatMoney(p.payment_total_amount)} total</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExpensePaymentMappingReport() {
  const masters = useMasters();
  const [bounds, setBounds] = useState(null);
  const [range, setRange] = useState(null);
  const [projectId, setProjectId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("");
  const [rows, setRows] = useState(null);
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => {
      setBounds(res.data);
      const allTime = buildPresets(res.data).find((p) => p.label === "All Time");
      setRange({ from: allTime.from, to: allTime.to });
    });
  }, []);

  useEffect(() => { setSubCategoryId(""); }, [categoryId]);

  useEffect(() => {
    if (!range) return;
    const params = { date_from: range.from, date_to: range.to };
    if (projectId) params.project_id = projectId;
    if (categoryId) params.category_id = categoryId;
    if (subCategoryId) params.sub_category_id = subCategoryId;
    if (sourceType) params.source_type = sourceType;
    if (paymentStatus) params.payment_status = paymentStatus;
    client.get("/reports/expense-payment-mapping", { params }).then((res) => {
      setRows(res.data);
      // Default to expanded so the mapping is visible without extra clicks.
      setExpandedIds(new Set(res.data.filter((r) => r.payments.length > 0).map((r) => r.expense_id)));
    });
  }, [range, projectId, categoryId, subCategoryId, sourceType, paymentStatus]);

  function toggle(id) {
    setExpandedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function expandAll() { setRows((r) => { setExpandedIds(new Set((r || []).filter((x) => x.payments.length > 0).map((x) => x.expense_id))); return r; }); }
  function collapseAll() { setExpandedIds(new Set()); }

  const splitPaymentCount = rows ? new Set(rows.flatMap((r) => r.payments.filter((p) => p.covers_multiple_expenses).map((p) => p.payment_id))).size : 0;

  return (
    <div className="space-y-6">
      <Link to="/reports" className="text-sm text-brand-600 hover:underline inline-flex items-center gap-1"><ArrowLeft size={14} /> All Reports</Link>
      <div>
        <h1 className="text-2xl font-display font-semibold">Expense ↔ Payment Mapping</h1>
        <p className="text-sm text-ink/50 mt-0.5">Every expense with the payment(s) that settled it. A payment split across several expenses is flagged wherever it appears.</p>
      </div>

      {range && (
        <Card>
          <div className="flex flex-wrap items-end gap-4">
            <DateRangePicker value={range} onChange={setRange} bounds={bounds} />
            <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">All Projects</option>
              {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Select label="Source" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
              <option value="">All Sources</option>
              {SOURCE_TYPES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
            <Select label="Head" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">All Heads</option>
              {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Sub-Head" value={subCategoryId} onChange={(e) => setSubCategoryId(e.target.value)} disabled={!categoryId}>
              <option value="">All Sub-Heads</option>
              {masters.subCategories.filter((s) => String(s.category_id) === String(categoryId)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <Select label="Payment" value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)}>
              <option value="">All Payment Statuses</option>
              {PAYMENT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
        </Card>
      )}

      {rows && (
        <>
          {splitPaymentCount > 0 && (
            <div className="text-xs text-warn bg-warn/10 rounded-md px-3 py-2 inline-flex items-center gap-1.5">
              <Split size={13} /> {splitPaymentCount} payment{splitPaymentCount > 1 ? "s" : ""} in this view cover more than one expense — expand a row to see which.
            </div>
          )}

          <Card>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-ink/50">{rows.length} expense(s)</div>
              <div className="flex gap-3">
                <button type="button" onClick={expandAll} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline"><ChevronsDown size={13} /> Expand All</button>
                <button type="button" onClick={collapseAll} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline"><ChevronsUp size={13} /> Collapse All</button>
              </div>
            </div>

            <div className="flex items-center gap-3 px-3 py-2 border-b border-ink/10 text-[11px] uppercase tracking-wide text-ink/40 font-medium">
              <span className="w-4 shrink-0" />
              <span className="w-32 shrink-0">Expense #</span>
              <span className="w-24 shrink-0">Date</span>
              <span className="w-32 shrink-0">Source</span>
              <span className="flex-1 min-w-0">Payee</span>
              <span className="w-40 shrink-0">Head / Sub-Head</span>
              <span className="w-28 shrink-0 text-right">Amount</span>
              <span className="w-28 shrink-0 text-right">Paid</span>
              <span className="w-28 shrink-0 text-right">Balance</span>
              <span className="w-32 shrink-0 text-right">Status</span>
            </div>

            {rows.length === 0 ? (
              <div className="text-sm text-ink/40 py-10 text-center">No expenses for this filter.</div>
            ) : (
              rows.map((row) => (
                <ExpenseRow key={row.expense_id} row={row} expanded={expandedIds.has(row.expense_id)} onToggle={toggle} />
              ))
            )}
          </Card>
        </>
      )}
    </div>
  );
}
