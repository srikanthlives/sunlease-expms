# CLAUDE.md — Expense & Payment Management System

Context file for continuing work on this project. Read this before making changes.

## What this is
Full-stack expense/invoice/payment/employee-claim system.
- Backend: FastAPI + SQLAlchemy + SQLite, at `backend/`
- Frontend: React + Vite + Tailwind, at `frontend/`
- Source of truth for setup: `README.md` in repo root.

## Core architecture (stable, don't relitigate)
- Every financial transaction (invoice, direct expense, or an approved employee-claim line) resolves into a row in the unified `expenses` table. `payment_status` (UNPAID/PARTIALLY_PAID/PAID) is **never** set directly — it's always recomputed from `PaymentAllocation` rows via `payment_status_service.recalculate_payment_status`.
- Financial records are cancelled, never deleted (`status=CANCELLED`), with an audit log entry.
- `AuditLog` gets a row for every create/update/cancel/submit/approve/reject/pay action.
- Document uploads (`documents` table) attach to expenses/invoices/payments/claims/claim-lines, stored under `backend/uploads/YYYY/MM/<uuid>.ext` (never original filename), validated by extension+MIME+size.

## Roles (current, in order of privilege)
- **SUPER_ADMIN** — everything. Only role that can: create new Roles, create Admin or Super Admin users, reset any user's password, enable/disable Admin or Super Admin accounts.
- **ADMIN** — controls the entire Masters section (Projects, Employees, Vendors, Accounts, Expense Categories) exclusively. Can create/disable Employee, Manager, and Accounts users — **cannot** create another Admin or a Super Admin (privilege-escalation guard, enforced server-side). Cannot create roles or reset passwords.
- **ACCOUNTS** — does all transactional work: direct expenses, invoices, payments, payment allocation, second-level (final) claim approval. Cannot touch Masters (no create/edit on projects/employees/vendors/accounts/categories) and cannot create users or roles.
- **MANAGER** — is *also* an Employee record (has `employee_id` set, self-referential `Employee.manager_id` hierarchy). Submits their own claims like any employee, and does first-level approval for their **direct reports'** claims only. Must not see expenses/invoices/payments/reports/company-wide dashboard — those endpoints 403 for Manager.
- **EMPLOYEE** — drafts/submits/resubmits their own claims only. No access to expenses/invoices/payments/reports/dashboards beyond `/dashboard/my-claims`.
- **VIEWER** — read-only access to the full financial dashboard/reports (same visibility as Accounts, no write actions anywhere).

Permission shorthands live in `backend/app/core/deps.py` (`require_admin`, `require_accounts`, `require_non_employee`, etc.) — always extend those rather than hand-rolling role checks in routers.

## Employee Claim workflow — TWO-LEVEL APPROVAL (the feature currently being built)

States (`app/models/enums.py::ClaimStatus`):
`DRAFT → SUBMITTED → PENDING_ACCOUNTS_APPROVAL → APPROVED`, with `REJECTED` reachable from either `SUBMITTED` or `PENDING_ACCOUNTS_APPROVAL`, looping back to the employee for edit + resubmit (which restarts at `SUBMITTED`, i.e. back to level 1 — simplest and safest rule, avoids ambiguity about "resume at whichever level rejected").

Flow:
1. Employee (or Manager, since Manager is also an employee) creates a **DRAFT** claim with one or more lines, edits freely.
2. **Submit** → status `SUBMITTED`. Routes to the employee's manager (`Employee.manager_id` → that manager's `User` account) for level-1 review.
3. **Manager approves** → status `PENDING_ACCOUNTS_APPROVAL`. Only *that specific* manager (or Admin/Super Admin as bypass) may approve — enforced by checking `claim.employee.manager_id == actor.employee_id`.
4. **Manager rejects** → status `REJECTED`, reason required. Employee edits and resubmits → back to `SUBMITTED`.
5. Routes to the **Accounts person assigned to the claim's project** (`Project.accounts_approver_id`, a `User` with role ACCOUNTS/ADMIN/SUPER_ADMIN) for level-2 (final) review. If the project has no assigned approver, or the claim has no project, **any** Accounts user (or Admin/Super Admin) may act — fallback pool.
6. **Accounts approves** → status `APPROVED`. This is the point where expenses actually get created (one `Expense` per claim line, exactly like the old single-level `approve_claim` did) — final, ready for payment via the normal Payments flow.
7. **Accounts rejects** → status `REJECTED`, same as step 4.

Authorization pattern to implement in `claim_service.py`:
```python
def _authorize_manager_approval(claim, actor):
    if actor.role.name in (SUPER_ADMIN, ADMIN): return
    if actor.role.name != MANAGER or not actor.employee_id: raise 403
    if claim.employee.manager_id != actor.employee_id: raise 403 "not this employee's manager"

def _authorize_accounts_approval(claim, actor):
    if actor.role.name in (SUPER_ADMIN, ADMIN): return
    if actor.role.name != ACCOUNTS: raise 403
    project = claim.project
    if project and project.accounts_approver_id and project.accounts_approver_id != actor.id:
        raise 403 "not the assigned approver for this project"
```
`approve_claim(db, claim, actor)` branches on `claim.status`: if `SUBMITTED` → level-1 (authorize_manager, set `PENDING_ACCOUNTS_APPROVAL`); if `PENDING_ACCOUNTS_APPROVAL` → level-2 (authorize_accounts, create expenses, set `APPROVED`). Same branching in `reject_claim`.

## Data model additions for this feature (done)
- `Project.accounts_approver_id` → FK to `users.id`, nullable. Set via `POST /projects/{id}/assign-approver` (Admin/Super Admin only), body `{user_id}` (null clears it). Target user must have role ACCOUNTS/ADMIN/SUPER_ADMIN.
- `Employee.manager_id` already existed (self-referential FK) — this is the hierarchy source of truth. No schema change needed there, just make sure the Employees master UI actually lets Admin pick a manager and project via dropdowns (today it's a generic text-field form — needs a dedicated component like `CategoriesMaster`).

## Router-level changes needed for claims.py (not yet done as of this file being written)
- `list_claims`: role-aware filtering —
  - EMPLOYEE: always forced to own claims regardless of params.
  - MANAGER: `mine=true` → own claims; `pending_for_me=true` → direct reports' `SUBMITTED` claims; default (no params) → all direct reports' claims (any status), never company-wide.
  - ACCOUNTS: `pending_for_me=true` → `PENDING_ACCOUNTS_APPROVAL` claims where project's approver is them (or fallback pool); otherwise full visibility (they "do all the things").
  - ADMIN/SUPER_ADMIN: full visibility always; `pending_for_me=true` → both SUBMITTED and PENDING_ACCOUNTS_APPROVAL org-wide.
  - VIEWER: full read visibility, no actions.
- `get_claim`: viewable by owner, that employee's manager, the project's assigned accounts approver, or Admin/Super Admin/Accounts (full visibility for Accounts).
- `update_claim` / `submit_claim`: owner or Admin/Super Admin only (not Accounts, not Manager-on-someone-else's-claim).
- `approve_claim` / `reject_claim` endpoints: router-level dependency allows MANAGER/ACCOUNTS/ADMIN/SUPER_ADMIN to call (block EMPLOYEE/VIEWER), then the service-layer `_authorize_*` functions do the fine-grained per-claim check described above.

## Frontend changes needed (not yet done as of this file being written)
- `ManagerDashboard.jsx`: **remove** the embedded `FinancialDashboard`/"Company Overview" section entirely (Manager must not see company financials). Keep: pending-approvals-from-direct-reports card (via `/dashboard/approvals`, now correctly team-scoped server-side) + the manager's own claim summary (reuse `/dashboard/my-claims`, same as Employee).
- New `AccountsDashboard.jsx`: `FinancialDashboard` (unchanged) **plus** a new "Claims Pending My Approval" card sourced from `/dashboard/accounts-approvals`. Wire into `Dashboard.jsx` role router for `ACCOUNTS`.
- `Dashboard.jsx` router: EMPLOYEE → EmployeeDashboard; MANAGER → ManagerDashboard (updated); ACCOUNTS → new AccountsDashboard; everyone else (ADMIN/SUPER_ADMIN/VIEWER) → FinancialDashboard.
- `MainLayout.jsx` nav:
  - "Masters" section: roles `["ADMIN","SUPER_ADMIN"]` only (drop ACCOUNTS).
  - "Transactions" section (Expenses/Invoices/Payments/Employee Claims list): roles `["ADMIN","SUPER_ADMIN","ACCOUNTS","VIEWER"]` (drop MANAGER).
  - "Reports": same set, drop MANAGER.
  - "My Work" (My Claims): roles `["EMPLOYEE","MANAGER"]` (Manager needs this too, since Manager submits their own claims).
  - "Approvals" (Claim Approvals): keep `["ADMIN","SUPER_ADMIN","MANAGER","ACCOUNTS"]`.
- `Claims.jsx`:
  - `ClaimsList` `approvalsOnly` mode should call `GET /claims?pending_for_me=true` instead of hardcoding `status_=SUBMITTED`, so it's correct for both Manager (sees SUBMITTED-from-reports) and Accounts (sees PENDING_ACCOUNTS_APPROVAL-for-their-projects) automatically.
  - `canCreate`: owner (`mineOnly`) or ADMIN/SUPER_ADMIN only — remove ACCOUNTS from claim-creation rights (claims are an employee action).
  - `ClaimDetail`: compute `canApprove` as `ADMIN/SUPER_ADMIN` always, or `MANAGER && claim.status === "SUBMITTED"`, or `ACCOUNTS && claim.status === "PENDING_ACCOUNTS_APPROVAL"`. Backend still authorizes precisely — frontend button visibility is just UX, not the security boundary.
- `components/ui.jsx`: add a `STATUS_STYLES` entry for `PENDING_ACCOUNTS_APPROVAL`.
- `pages/Masters.jsx`: replace the generic-form `EmployeesMaster` with a dedicated component that has proper `<select>` dropdowns for Project and Manager (list of existing employees) — this is what actually lets Admin build the hierarchy. Replace `ProjectsMaster` similarly to include an "Assign Approver" action per row (dropdown of Accounts/Admin/Super Admin users, calling `POST /projects/{id}/assign-approver`).
- `pages/UsersAdmin.jsx`: the role dropdown in the "New User" form must exclude ADMIN and SUPER_ADMIN when the actor is an ordinary Admin (only Super Admin can grant those) — mirrors the backend guard already in `auth.py::create_user`. Also add an `employee_id` picker to the user-creation form so new Employee/Manager users can be linked to their Employee master record at creation time (currently missing — without it you can't set up the hierarchy end-to-end from the UI).

## auth.py change needed (not yet done)
`create_user`: currently only blocks granting SUPER_ADMIN unless actor is SUPER_ADMIN. Extend the same guard to ADMIN: *only* SUPER_ADMIN may create a user with role ADMIN or SUPER_ADMIN. Ordinary Admin may create EMPLOYEE, MANAGER, ACCOUNTS (and VIEWER) only.

## Testing pattern used throughout this project
**Never `rm -f expms.db` as a routine step.** The dev database holds real
working data across sessions and must survive schema changes. After every
backend model change, just restart uvicorn - `app/migrate.py` runs
automatically on startup and additively applies the diff (new tables/columns)
with zero data loss (verified repeatedly, e.g. by rebuilding `expenses` and
`employee_claims` without their newest columns on a copy of a live db, then
confirming `migrate()` restored the columns with every existing row intact).
Only reset the database (`rm -f expms.db && python -m app.seed`) if the user
explicitly asks for a clean slate, or a model change needs a rename/retype
that `migrate.py` can't do automatically (see its docstring and the
"Auto-migration script" section below) - and even then, ask first rather than
doing it silently.

Start uvicorn with `nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 < /dev/null &` followed by `disown` (macOS/zsh has no
`setsid`; on Linux `setsid ... &` also works) - it must be started in its own
tool call, since background processes die at tool-call boundaries in this
environment, so starting the server and immediately curling it in the *same*
bash call fails; start it, then in the *next* tool call run tests against it.
Drive it with `requests` in Python (backend venv: `.venv/bin/python3`, install
`requests` into it if missing) covering both the happy path and the 403/400
guardrails. Always re-run the full existing regression (invoice→payment→PAID,
claim submit→approve, dashboard endpoints) after any permission change, since
these have broken silently before. `pkill -f "uvicorn app.main:app"` to stop
the test server when done.

After every frontend change: `cd frontend && npm install -q && npm run build` must succeed with zero errors before considering the change done.

Before repackaging the deliverable zip: clean `backend/expms.db`, `backend/uploads/2026` (or whatever the current test-run date bucket is), all `__pycache__`, `frontend/node_modules`, `frontend/dist` — then `zip -rq /mnt/user-data/outputs/expense_payment_management_system.zip expms -x ...`. Always verify the zip's contents with a throwaway extract + grep before calling `present_files`, because zip commands have silently no-opped mid-task before in this environment (stale timestamp on the output file is the tell).

## Seed data note
`seed.py` needs updating once the hierarchy UI exists: add at least one Manager (Employee + User with role MANAGER, `employee.manager_id` pointing nowhere/null since they're top-level), one more Employee reporting to that Manager (`manager_id` = the manager's employee id), and assign the seeded project's `accounts_approver_id` to the `accounts` user — otherwise there's no way to manually test the full two-level flow immediately after a fresh seed.

## Post-implementation UI review pass (done)
No browser automation tool is available in this environment, so instead of
visually clicking through the app, a careful code-level review pass was done
looking for the class of bugs that only surface in a real browser. Found and
fixed two real issues:
1. `EmployeeDashboard.jsx` still had a stale `STATUS_ORDER` array referencing
   the old `UNDER_REVIEW` status instead of `PENDING_ACCOUNTS_APPROVAL` -
   claims sitting at that stage were silently missing from the "Claims by
   Status" breakdown (still counted in the total, just invisible as a
   category). Verified against a live claim actually in that state.
2. `UsersAdmin.jsx` showed the Disable/Enable button on every user row
   regardless of target role, but the backend blocks an ordinary Admin from
   toggling another Admin/Super Admin (403) - fixed to hide the button
   client-side to match, rather than surfacing a confusing error.
Confirmed via `grep -rn "UNDER_REVIEW"` across both `frontend/src` and
`backend/app` that no other stale references remain.

## Consolidated single-expense claims (done)
Employee claim approval (level 2 / accounts) now creates exactly ONE
consolidated `Expense` record per claim, not one per line. Key points:
- `EmployeeClaim.expense_id` (new column) + `EmployeeClaim.expense_number`
  (Python `@property`, not mapped) expose the linked expense on the claim
  itself; `ClaimOut` schema surfaces both.
- All `EmployeeClaimLine.expense_id` values within a claim point to the
  same shared expense - kept for traceability/back-compat, not because
  lines have their own expense anymore.
- Category/sub-category: if every line shares the same expense head, that
  carries through to the consolidated expense (so single-purpose claims
  still report correctly by category). Mixed-category claims land as
  Uncategorised (`category_id=None`) rather than picking one arbitrarily.
- Description is auto-built from the claim description + a semicolon-joined
  summary of each line's description, e.g. `"Client trip — Taxi to
  airport; Taxi from airport; Hotel"`.
- `base_amount` = `claim.total_amount` (the sum, recalculated from lines at
  approval time same as before).
- Frontend (`Claims.jsx` `ClaimDetail`): removed the per-line "Expense"
  column (redundant once every line points to the same one) in favor of a
  single banner showing `claim.expense_number` once approved. Per-line
  attachment/proof upload is unchanged - that's independent of the
  consolidated accounting record.
- This is a schema change (new column on `employee_claims`). At the time this
  was written there was no auto-migration, so existing dev DBs needed a reset
  to pick it up. That's no longer true - see "Auto-migration script" below:
  `app/migrate.py` now applies additive changes like this automatically on
  every startup, no reset needed.

## Attachment count badge (done)
`components/Attachments.jsx` now loads the document list eagerly on mount
(previously lazy, only loaded when the modal was opened) so a small accent
badge showing the count can render directly on the trigger button without
requiring a click first. Still reloads on modal open for freshness, and
after every successful upload. No badge shown when count is 0.

## Edit support for Masters entries (done)
Every Masters entity now supports Edit, not just Create, gated to Admin/Super
Admin (same as create):
- Backend: added `PUT /projects/{id}`, `PUT /employees/{id}`,
  `PUT /vendors/{id}`, `PUT /categories/{id}`,
  `PUT /categories/{category_id}/sub-categories/{sub_id}`,
  `PUT /accounts/{id}` - all `require_admin`, all doing a full-payload
  replace (reuse the same `*Create` schema as the body), with duplicate-code/
  duplicate-name checks that correctly exclude the row being edited itself.
  Employee edit also re-validates the manager-cannot-be-self guard.
- Frontend: the generic `MasterPage` component (used by Vendors and
  Accounts) now tracks an `editingId` and switches between POST/PUT
  accordingly, with an "Edit" link per row. The three custom Masters pages
  (Employees, Projects, Categories) got the same treatment by hand since
  they don't use `MasterPage`. Categories page: category name has an inline
  pencil-edit; sub-category chips are now clickable to edit in place.
Tested all 6 edit endpoints plus their permission boundaries (Accounts
blocked, duplicate-code/name rejected, self-manager rejected) against the
live API - all pass.

## Edit approval workflow for Expenses/Invoices/Payments (done)
Admin and Super Admin edit posted Expenses/Invoices/Payments directly and
immediately (`PUT /expenses|invoices|payments/{id}`, require_admin). Accounts
proposes the same edits instead - they go into an approval queue and only
take effect once Admin/Super Admin approves.

- New `EditRequest` model/table: entity_type (EXPENSE/INVOICE/PAYMENT),
  entity_id, `changes` (JSON dict of field→new value), `previous_values`
  (JSON snapshot of the old values at request time, for the diff view),
  status (PENDING/APPROVED/REJECTED), requester, reviewer, timestamps,
  review remarks. This table **is** the "history of all approved and
  rejected edits" the person asked for - `GET /edit-requests` (Admin/Super
  Admin see everything; Accounts see only their own).
- `services/edit_request_service.py` centralizes ALL the business logic
  (field whitelist per entity, type coercion, FK existence checks, the
  amount-vs-already-paid guard, Invoice→linked-Expense mirroring) in one
  `apply_changes()` function, called identically by both the direct-edit
  path and the approve-edit-request path. This was a deliberate design
  choice so the two paths can never drift apart in what they allow.
- **Editable field whitelist** (anything else is rejected with 400):
  - Expense: expense_date, project_id, vendor_id, employee_id, category_id,
    sub_category_id, description, base_amount, gst_amount, other_amount
  - Invoice: invoice_number, vendor_id, invoice_date, due_date, project_id,
    description, taxable_amount, cgst, sgst, igst, other_tax, category_id,
    sub_category_id (last two apply to the linked Expense, since Invoice
    itself has no category field)
  - Payment: payment_date, account_id, payment_mode, reference_number,
    remarks - **deliberately excludes amount and allocations**. Editing a
    payment's amount would require re-validating every allocation against
    outstanding balances, which is a materially bigger feature; scoped out
    for now. Amount corrections go through cancel + re-pay instead (existing
    flow).
- **Guard rail**: reducing an Expense's or Invoice's total below what's
  already been paid against it is rejected with 400, both when Admin edits
  directly and when an edit request is approved (re-validated against
  CURRENT paid amount at approval time, not request time - more payments
  may have landed in between).
- Approving/rejecting an already-decided request is rejected with 400
  (no re-review). Only Accounts can create edit requests (403 for everyone
  else, including Employee/Manager/Viewer); only Admin/Super Admin can
  approve/reject (403 for Accounts, including on their own requests -
  no self-approval).
- Frontend: `components/EditEntityModal.jsx` is the single edit form,
  role-aware - same UI either way, but submits to `PUT .../{id}` directly
  for Admin/Super Admin or to `POST /edit-requests` for Accounts (with a
  "submitted for approval, nothing changed yet" confirmation state instead
  of the usual "saved"). Wired into the Edit buttons on `Expenses.jsx`,
  `Invoices.jsx`, `Payments.jsx`. `pages/EditRequests.jsx` is the review
  queue + history, nav-gated to Admin/Super Admin/Accounts under a new
  "Edit Requests" sidebar section.
- Only fields that actually changed are sent (both to keep edit-request
  diffs clean and so direct edits don't touch untouched columns) - computed
  client-side in `EditEntityModal.buildChanges()`.

Tested: direct admin edit + guard against reducing total below paid amount;
Accounts blocked from direct edit; edit request submit → entity provably
unchanged while pending → Admin approves → change applied → re-approve
rejected; Admin rejects with required reason → entity provably unchanged
(verified with a purpose-created tracked entity, not just an incidental
list[0] which masked a false-positive in an earlier draft of this test);
Accounts self-approval blocked; non-whitelisted field rejected; invalid
entity_type rejected; Invoice amount edit correctly mirrors to its linked
Expense; Payment metadata edit; full history/filtering by status; Manager
has zero access to any of this (403). Also re-ran the full existing
regression suite (invoice+payment, two-level claim approval) afterward -
no regressions.

## Auto-migration script (done)
`backend/app/migrate.py` replaces the plain `Base.metadata.create_all()`
call. On every app startup (wired into `main.py`) and via
`python -m app.migrate` for an explicit/verbose run, it diffs the live
SQLite DB against the current models and additively applies the
difference: creates any new table, adds any new column to an existing
table. It never drops, renames, or retypes anything - those need a full
SQLite table rebuild to do safely, so they're left for a human (or a real
Alembic migration, if this ever graduates past SQLite/dev use).

Implementation note: iterates `Base.metadata.tables.values()` rather than
`Base.metadata.sorted_tables` - this project has a genuine circular FK
(`Project.accounts_approver_id -> User -> Employee.project_id -> Project`)
that trips SQLAlchemy's topological sort with a `SAWarning`. SQLite doesn't
enforce FK ordering at `CREATE TABLE` time regardless, so leaving table
creation unordered is safe here and avoids the warning entirely.

`seed.py` calls `migrate(verbose=True)` instead of `create_all()` too, so
re-running seed against an older on-disk DB (rather than a fresh one)
no longer crashes on missing columns.

**Tested for real, not just structurally**: took a fully-seeded DB, used
raw SQL to rebuild `projects` and `employee_claims` without their most
recently added columns (`accounts_approver_id`, `expense_id`) and dropped
the `edit_requests` table entirely - genuinely reproducing what an old
pre-these-features database would look like, with real existing data
still in the other tables. Ran `python -m app.migrate`: added both missing
columns and recreated the missing table, zero data loss on unrelated
tables (5 seeded users, the GEN project's code/name all intact). Then
booted the actual API server against that migrated DB and exercised every
affected code path through the ORM - project approver assignment, the
full two-level claim approval flow (which needs `EmployeeClaim.expense_id`
on the newly-added column), and a full edit-request approve cycle on the
newly-created table - all worked correctly. Also confirmed idempotency
(second run reports "nothing to do") and that plain `uvicorn app.main:app`
startup alone (no manual migrate step) self-heals the schema, which is
the actual point of this feature.

**Boundary to know**: this only handles additive changes automatically.
If a future model change renames or removes a field, or changes a
column's type, `migrate.py` will not touch it - you'll need to write a
one-off manual `ALTER TABLE`/data-migration for that specific change, or
just reset the dev DB if the data isn't precious.

## Reports: split into independent pages + date-range everywhere (done)
Reports moved from one tabbed page to independent routed pages under
`frontend/src/pages/reports/`, linked from a `ReportsHub.jsx` card grid at
`/reports`:
- `/reports/daily-register` - single day, prev/next day nav
- `/reports/trend` - **replaces the earlier Monthly/Yearly split** - a
  single page with a free date-range picker (see below), month-bucketed
  chart + table, optional project filter
- `/reports/project-wise`, `/reports/vendor-outstanding`,
  `/reports/employee-wise` - same date-range picker instead of the year
  dropdown they briefly had

**Important history**: this went through two iterations in one session.
First pass added fixed Monthly/Yearly report pages with year dropdowns
(`GET /reports/monthly-summary`, `GET /reports/yearly-summary`,
`GET /reports/available-years`). The person then asked to replace
month/year buckets with a freely-choosable date range instead - those
three endpoints were removed entirely (verified 404 on all three) and
replaced with:
- `GET /reports/trend?date_from=&date_to=&project_id=` - buckets by
  calendar month across the range, but **clips each bucket to the actual
  requested dates** (a range starting Jan 16 correctly excludes a Jan 15
  expense, not just whole-month matching). Defaults to the last ~5 months
  up to today when no range is given. Rejects `date_from > date_to` with 400.
- `GET /reports/date-bounds` - earliest/latest expense_date with activity,
  used by the frontend to build preset ranges (see below) and as the
  "All Time" bound.
- `project-wise`, `vendor-outstanding`, `employee-wise` now take
  `date_from`/`date_to` query params (inclusive) instead of `year`.

`components/DateRangePicker.jsx` is the shared control: a From/To date pair
plus preset buttons (This Month, Last 3 Months, Last 6 Months, This Year,
Last 12 Months, All Time) computed client-side in `buildPresets(bounds)`
from the `/reports/date-bounds` response. Every date-range report page
follows the same pattern: fetch bounds on mount → default to a sensible
range → refetch its data whenever `range` or `project_id` changes.

`components/charts.jsx` has two small dependency-free chart primitives used
across all report pages (`VerticalBarChart` for expense/payment trend,
`HorizontalBreakdownList` for proportional per-row breakdowns like paid vs
outstanding) - deliberately CSS/SVG-based rather than pulling in a charting
library, consistent with the existing dashboard's style.

**Payments and project filtering**: `Payment` has no `project_id` column
directly - project-scoped payment sums (in `/reports/trend`) go through a
join on `PaymentAllocation -> Expense.project_id` instead. Tested and
correct.

Tested thoroughly against the live API: month-bucket totals across a range
spanning a year boundary (Dec 2025 - Apr 2026), exact-date clipping
(excluding an expense one day outside a tightly-scoped range), the
project-filtered payment join, invalid range rejection (400), old
endpoints genuinely gone (404), and Manager still blocked from every
report endpoint (403). One real mistake caught and fixed during this work:
a test run against a stale `expms.db` that hadn't actually been reset
produced doubled totals - not an app bug, but a reminder that `rm -f
expms.db` and the subsequent `python -m app.seed` need to be verified as
having actually completed (check `ls` / query the DB directly) before
trusting a test's data assumptions, since background/chained shell commands
in this environment can be silently killed mid-sequence at tool-call
boundaries.

## Project-wise dashboard (done)
`GET /dashboard` now accepts an optional `project_id` query param that
pivots every figure on the dashboard from company-wide to that single
project - today's/month expenses, payments, outstanding, pending claims,
category breakdown, and the 6-month trend chart. No new endpoint - the
existing one just got project-aware.

- When `project_id` is given, the response includes a `project` block
  (code, name, description, assigned Accounts approver's display name,
  all-time expense/paid/outstanding for that project specifically) and
  omits `expense_by_project` (redundant once already scoped to one).
- When omitted, behaves exactly as before (company-wide, `expense_by_project`
  present, no `project` key) - fully backward compatible.
- Same payment-project-join pattern as the Trend Report: `Payment` has no
  `project_id` column, so project-scoped payment sums go through
  `PaymentAllocation -> Expense.project_id` instead of the payment table
  directly. Applies to today's payments and every month in the trend.
- `all_time_paid`/`all_time_outstanding` in the project block sum actual
  paid amounts per expense (`get_paid_amount`), not `total_amount` of
  fully-PAID expenses only - **a real bug caught by testing**: the first
  version filtered `Expense.payment_status == "PAID"` before summing,
  which silently ignored partially-paid expenses and reported a
  partially-paid project's paid-so-far as ₹0. Fixed and reverified with a
  project that had exactly one partial payment (400 of 1000) - now
  correctly shows `all_time_paid: 400.0`, not `0.0`.
- Same permission boundary as before: Admin/Super Admin/Accounts/Viewer
  only; Manager gets 403 even with a `project_id` (tested explicitly,
  since a query param could plausibly have been overlooked as a bypass).
- Invalid `project_id` -> 404, not a silently-empty dashboard.

Frontend: `FinancialDashboard.jsx` (used standalone for Admin/Super
Admin/Viewer, and embedded inside `AccountsDashboard.jsx`) gained a
project `<Select>` in its header. Selecting a project refetches with
`project_id` and renders a project info banner (code, approver, all-time
totals) above the usual stat cards; the "Expense by Project" breakdown
card is only shown when unscoped (all projects), and each row in it is
now clickable to jump straight into that project's scoped view - a
natural drill-down path from "which project is spending the most" to
"let me look at that project specifically" without leaving the dashboard.
Tested: company-wide vs two isolated projects' activity on the same day
(1000/400 paid vs 500/500 paid) - each project's dashboard correctly shows
only its own numbers, confirmed against the live API before touching the
frontend.
