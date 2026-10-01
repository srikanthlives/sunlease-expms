import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../../api/client";
import { useMasters } from "../../hooks/useMasters";
import { Card, Select, StatusBadge, formatMoney, formatDate } from "../../components/ui";
import DateRangePicker, { buildPresets } from "../../components/DateRangePicker";
import MultiSelect from "../../components/MultiSelect";
import Attachments from "../../components/Attachments";
import { ArrowLeft, ChevronDown, ChevronRight, ChevronsDown, ChevronsUp, ChevronLeft, Wallet, Split } from "lucide-react";

const SOURCE_TYPES = ["EXPENSE", "INVOICE", "EMPLOYEE_CLAIM"];
const PAYMENT_STATUSES = ["UNPAID", "PARTIALLY_PAID", "PAID"];
const PAGE_SIZES = [25, 50, 100];

// One shared column template for header and rows so every value lines up.
const GRID = "grid items-center gap-3 grid-cols-[1rem_7rem_5.5rem_7rem_6.5rem_minmax(7rem,1fr)_minmax(9rem,1.4fr)_minmax(8rem,1fr)_6.5rem_6.5rem_6.5rem_7.5rem]";

function expenseAttachmentsProps(row) {
  if (row.source_type === "INVOICE") return { documentType: "INVOICE", invoiceId: row.source_id };
  if (row.source_type === "EMPLOYEE_CLAIM") return { claimFullId: row.source_id };
  return { documentType: "EXPENSE", expenseId: row.expense_id };
}

function ExpenseRow({ row, expanded, onToggle }) {
  const hasPayments = row.payments.length > 0;
  return (
    <div className="border-b border-ink/10 last:border-0">
      <div className={`w-full flex items-center gap-3 px-3 py-3 ${hasPayments ? "hover:bg-brand-50" : ""}`}>
        <button
          type="button"
          onClick={() => hasPayments && onToggle(row.expense_id)}
          className={`${GRID} flex-1 min-w-0 text-left ${hasPayments ? "cursor-pointer" : "cursor-default"}`}
        >
          <span className="text-ink/30">
            {hasPayments ? (expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : null}
          </span>
          <span className="font-medium text-sm truncate" title={row.expense_number}>{row.expense_number}</span>
          <span className="text-xs text-ink/50 whitespace-nowrap">{formatDate(row.expense_date)}</span>
          <span className="text-[11px] text-ink/40 uppercase truncate" title={row.source_type.replace(/_/g, " ")}>
            {row.source_type.replace(/_/g, " ")}
          </span>
          <span className="text-sm truncate" title={row.bill_number || ""}>{row.bill_number || "—"}</span>
          <span className="text-sm truncate" title={row.payee}>{row.payee}</span>
          <span className="text-xs text-ink/60 truncate" title={row.description || ""}>{row.description || "—"}</span>
          <span className="text-xs text-ink/50 truncate" title={`${row.category_name}${row.sub_category_name ? " / " + row.sub_category_name : ""}`}>
            {row.category_name}{row.sub_category_name ? ` / ${row.sub_category_name}` : ""}
          </span>
          <span className="text-right tabular text-sm">{formatMoney(row.total_amount)}</span>
          <span className="text-right tabular text-sm text-ok">{formatMoney(row.paid_amount)}</span>
          <span className="text-right tabular text-sm text-warn">{formatMoney(row.balance_due)}</span>
          <span className="flex justify-end"><StatusBadge status={row.payment_status} /></span>
        </button>
        <div className="w-10 shrink-0 flex justify-center" onClick={(e) => e.stopPropagation()}>
          <Attachments {...expenseAttachmentsProps(row)} compact readOnly label="Proof / Bill" />
        </div>
      </div>

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
              <div className="shrink-0">
                <Attachments documentType="PAYMENT" paymentId={p.payment_id} compact readOnly label="Receipt" />
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
  const [projectId, setProjectId] = useState([]);
  const [categoryId, setCategoryId] = useState([]);
  const [subCategoryId, setSubCategoryId] = useState([]);
  const [sourceType, setSourceType] = useState([]);
  const [paymentStatus, setPaymentStatus] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [rows, setRows] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  useEffect(() => {
    client.get("/reports/date-bounds").then((res) => {
      setBounds(res.data);
      const allTime = buildPresets(res.data).find((p) => p.label === "All Time");
      setRange({ from: allTime.from, to: allTime.to });
    });
  }, []);

  useEffect(() => { setSubCategoryId([]); }, [categoryId]);
  useEffect(() => { setPage(1); }, [range, projectId, categoryId, subCategoryId, sourceType, paymentStatus, pageSize]);

  useEffect(() => {
    if (!range) return;
    const params = { date_from: range.from, date_to: range.to, page, page_size: pageSize };
    if (projectId.length) params.project_id = projectId.join(",");
    if (categoryId.length) params.category_id = categoryId.join(",");
    if (subCategoryId.length) params.sub_category_id = subCategoryId.join(",");
    if (sourceType.length) params.source_type = sourceType.join(",");
    if (paymentStatus.length) params.payment_status = paymentStatus.join(",");
    client.get("/reports/expense-payment-mapping", { params }).then((res) => {
      setRows(res.data.rows);
      setTotalCount(res.data.count);
      // Default to expanded so the mapping is visible without extra clicks.
      setExpandedIds(new Set(res.data.rows.filter((r) => r.payments.length > 0).map((r) => r.expense_id)));
    });
  }, [range, projectId, categoryId, subCategoryId, sourceType, paymentStatus, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

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
          </div>
          <div className="flex flex-wrap items-end gap-4 mt-4 pt-4 border-t border-ink/10">
            <MultiSelect label="Project" className="w-44" placeholder="All Projects" value={projectId} onChange={setProjectId}
              options={masters.projects.map((p) => ({ value: p.id, label: p.name }))} />
            <MultiSelect label="Source" className="w-44" placeholder="All Sources" value={sourceType} onChange={setSourceType}
              options={SOURCE_TYPES.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))} />
            <MultiSelect label="Head" className="w-44" placeholder="All Heads" value={categoryId} onChange={setCategoryId}
              options={masters.categories.map((c) => ({ value: c.id, label: c.name }))} />
            <MultiSelect label="Sub-Head" className="w-44" placeholder="All Sub-Heads" value={subCategoryId} onChange={setSubCategoryId}
              disabled={categoryId.length === 0}
              options={masters.subCategories.filter((s) => categoryId.includes(String(s.category_id))).map((s) => ({ value: s.id, label: s.name }))} />
            <MultiSelect label="Payment" className="w-44" placeholder="All Payment Statuses" value={paymentStatus} onChange={setPaymentStatus}
              options={PAYMENT_STATUSES.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))} />
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
              <div className="text-xs text-ink/50">{totalCount} expense(s)</div>
              <div className="flex gap-3">
                <button type="button" onClick={expandAll} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline"><ChevronsDown size={13} /> Expand All</button>
                <button type="button" onClick={collapseAll} className="text-xs inline-flex items-center gap-1 text-brand-700 hover:underline"><ChevronsUp size={13} /> Collapse All</button>
              </div>
            </div>

            <div className="overflow-x-auto">
            <div className="min-w-[1250px]">
            <div className="flex items-center gap-3 px-3 py-2 border-b border-ink/10 text-[11px] uppercase tracking-wide text-ink/40 font-medium">
              <div className={`${GRID} flex-1`}>
                <span />
                <span>Expense #</span>
                <span>Date</span>
                <span>Source</span>
                <span>Bill No</span>
                <span>Payee</span>
                <span>Description</span>
                <span>Head / Sub-Head</span>
                <span className="text-right">Amount</span>
                <span className="text-right">Paid</span>
                <span className="text-right">Balance</span>
                <span className="text-right">Status</span>
              </div>
              <span className="w-10 shrink-0" />
            </div>

            {rows.length === 0 ? (
              <div className="text-sm text-ink/40 py-10 text-center">No expenses for this filter.</div>
            ) : (
              rows.map((row) => (
                <ExpenseRow key={row.expense_id} row={row} expanded={expandedIds.has(row.expense_id)} onToggle={toggle} />
              ))
            )}
            </div>
            </div>

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
                <span>Page {page} of {totalPages} · {totalCount} total</span>
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
          </Card>
        </>
      )}
    </div>
  );
}
