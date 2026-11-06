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

## Funds: repayments to funding entities + loan/capital split (done)
`FundTransfer.kind` gained a third value, **`REPAYMENT`** - the mirror image
of `FUNDING`: money going back OUT of one of our accounts to a funding
entity (repaying a director's loan, returning capital, settling an
advance). `from_account_id` required, `to_account_id` null,
`funding_entity_id` required (defaults to the source account's own entity).
`FUNDING` is unchanged (to_account only), `TRANSFER` unchanged (both ends
are our own accounts).

New `FundTransfer.funding_type` column classifies FUNDING/REPAYMENT rows as
`LOAN` / `CAPITAL` / `ADVANCE` / `OTHER` (defaults to `LOAN` when omitted;
always null on TRANSFER rows) - this is what distinguishes a director's
*loan* from equity introduced. Validated server-side against the
`FUNDING_TYPES` tuple in `routers/funds.py`.

Balance sheet (`GET /funds/balance-sheet`):
- per-account `repaid` figure, and `balance` now subtracts it
  (`opening + funded + transfers_in + receipts − transfers_out − repaid − payments`)
- per-entity `total_repaid` and `net_funded` (= funded − repaid, i.e. what
  the business still owes/holds from that entity), plus `by_funding_type`:
  net outstanding broken down by LOAN/CAPITAL/ADVANCE
- same three keys on the grand `totals`
`GET /funds/transfers` gained `kind` and `funding_type` filters.

Frontend `pages/Funds.jsx`: the transfer form's Type dropdown has the third
option and swaps which account field it asks for per kind (plus a "Nature"
dropdown for FUNDING/REPAYMENT); the transfers table shows
`Kind · Nature` and renders the entity name in the To column for
repayments; the balance sheet has a "Repaid Out" column, a "Repaid to
Funders" / "Net Funding Outstanding" stat pair, and per-entity
loan-vs-capital chips.

**Schema note - `app/fixups.py` (new)**: this needed
`fund_transfers.to_account_id` to become nullable, which `migrate.py`
deliberately won't do (additive-only; SQLite can't ALTER nullability).
`fixups.py` holds hand-written, idempotent, one-transaction-each schema
rebuilds for exactly this class of change, runs from `main.py` right after
`migrate()`, and is runnable standalone with `python -m app.fixups`. The
one fixup in it renames `fund_transfers` aside, drops the indexes that
SQLite carries across the rename (they keep their names and would
collide), recreates the table from the model, copies every row back, and
drops the old table. Put future non-additive changes here rather than
reaching for a DB reset.
Tested against the live API: funding in (loan + capital), partial
repayment out, every 400 guard rail (repayment with a to_account, without
a from_account, funding with a from_account, bad funding_type, bad kind,
zero amount, same-account transfer), entity totals/net/by-type arithmetic,
account balance net of the repayment, cancelled repayment excluded from
all totals, both new list filters, and non-Super-Admin (admin/accounts/
manager) blocked from the whole module. Fixup verified separately on a
copy of the live DB with a pre-existing row: rebuilt correctly, row and
unique index intact, second run a no-op.

**Note on the DB path**: the live dev database is `data/expms.db` (see
`EXPMS_DATABASE_URL` default in `core/config.py`), *not*
`backend/expms.db` - that file exists but is empty and stale. Earlier
notes in this file saying `rm -f expms.db` mean the one under `data/`.

## App-wide: description popup, textarea entry, 2000-char cap (done)
Three related changes rolled out across every page, not just Funds.

**1. `TruncatedText` everywhere a description appears.** Every
description / remarks / notes / po_number column in every table now uses
the shared `TruncatedText` cell (see its own section below) instead of a
hand-rolled truncation. Replaced four different ad-hoc patterns that had
accumulated: a `style={{width: "30ch"}}` + native `title=` tooltip
(Expenses, Invoices, Receivables x2), a `max-w-[160px] truncate` + title
(Payments, RecurringExpenses), and *un*truncated `whitespace-normal
break-words` blocks that made claim rows multiple lines tall (Claims x2).
Also added to the two columns that had no truncation at all (Masters
project description, UsersAdmin role description). Native `title=`
tooltips can't be copied, don't render multi-line text properly and are
slow to appear - that's the whole reason for the swap. Short identifier
columns (vendor/project/category name, bill number, payee) were left on
their existing `title=` truncation deliberately; they are labels, not
free text.

**2. Descriptions are entered in a textarea, not a one-line input.**
Converted 13 `<Input label="Description|Remarks|Notes|Reason">` fields to
`<Textarea>` across Claims (claim + line + reject reason), Expenses,
Invoices, Receivables x3, RecurringExpenses, RecurringExpenseApprovals,
Masters, UsersAdmin x2. `EditEntityModal`'s description/remarks fields
switched from `type: "text"` to `type: "textarea"` (which that component
already supported, and which also makes them span both form columns).
`Textarea` now defaults to **4 rows** (was 3).

**Behaviour change worth knowing**: `Input` auto-uppercases its value by
default (`NON_UPPERCASE_TYPES` in ui.jsx); `Textarea` does not. So newly
typed descriptions are no longer force-uppercased. Existing rows keep
whatever case they were stored with, so lists will show a mix for a
while. This is an improvement for paragraph-length text, but it is a
visible change, not an accident.

**3. A 2000-character cap on free text.** Note the schema reality: every
one of these fields is a SQLAlchemy `Text` column, and SQLite does not
length-limit `TEXT` at all - so there was no "database size" to validate
against. 2000 is a deliberate product limit (chosen by the user after
being told this), not a schema-derived one.
- Single source of truth: `TEXT_FIELD_MAX_LENGTH` in
  `app/schemas/common.py`, exposed as the `LongText` / `OptLongText`
  annotated Pydantic types. Mirrored by `TEXT_FIELD_MAX` in
  `components/ui.jsx` - the two must stay in sync, noted in both files.
- Applied to **request** schemas only (28 fields across auth, masters,
  transactions, receivables, recurring_expenses, edit_requests, plus the
  `EntityIn`/`TransferIn`/`CancelIn` models inside `routers/funds.py`).
  **Never to `*Out` response schemas** - constraining a response would
  make any pre-existing row longer than the cap unreadable through the
  API. Verified: a 5000-char description written directly to the DB still
  reads back in full.
- `edit_request_service.validate_fields()` got its own explicit length
  check, because edit requests carry a raw `changes` dict and so bypass
  Pydantic entirely - without it that path is a way around the cap.
- Frontend: `Textarea` sets `maxLength` and shows a live `n/2000` counter
  that turns amber in the last 10%. Pass `maxLength={0}` to opt out.

Tested against the live API: over-limit rejected 422 on project
description, expense description, claim description, claim *line*
description, funding-entity notes, fund-transfer remarks and cancel
reason; exactly 2000 accepted at the boundary and read back at full
length; the edit-request path rejected with 400 (and accepted at exactly
2000); and a pre-existing 5000-char value still readable. Frontend
`npm run build` and `npm run lint` clean (21 pre-existing warnings, none
in touched files). Full backend regression plus the documents and
verification suites re-run green.

**One trap hit while doing this**: a scripted replacement of
`TransferIn.remarks` silently no-opped because the real field order
differed from the pattern I matched, and the test for it was the only
reason it surfaced. Every scripted edit in this project should assert its
pattern matched before writing - several of the replacements here did,
that one did not.

## Funds: attachments on transfers / funding (done)
Transfers and funding entries take file attachments (bank advice, cheque
scan, signed acknowledgement) through the **existing** documents system
rather than anything new - `DocumentType.FUND_TRANSFER` plus
`Document.fund_transfer_id` (new nullable FK, additive so `migrate.py`
picked it up on restart).

- `POST /documents` accepts `fund_transfer_id` + `document_type=FUND_TRANSFER`;
  `GET /documents/by-entity?fund_transfer_id=`, download and delete all
  understand it. Same extension/MIME/size validation as every other upload.
- Storage folder: `DOCUMENT_FOLDER_FUND_TRANSFER` (env
  `EXPMS_DOCUMENT_FOLDER_FUND_TRANSFER`, default `fund-transfers`). A fund
  transfer has no project, so files land under the `default` project code,
  and - like claims - are grouped in a folder named after the **transfer
  number** rather than the upload date, so everything supporting FT-00007
  sits together: `<project>/default/fund-transfers/FT-00007/<uuid>.ext`.
- **Permissions are the important part.** Other document types allow any
  authenticated user to list/download; fund-transfer attachments instead
  inherit the Funds module's own boundary via
  `_authorize_fund_transfer_document()` - Admin/Super Admin only for
  upload, list, download *and* delete. Accounts/Super Accounts/Manager/
  Employee/Viewer get 403 on all four.
- The verification lock extends to attachments the same way Payments does
  it: once a transfer is verified only Super Admin can **delete** an
  attachment, but Admin can still add and view them - supporting proof
  isn't financial data, and attaching the bank advice after sign-off is a
  normal thing to want.
- Frontend: an Attachments column on the Transfers & Funding table reusing
  `components/Attachments.jsx` (which gained a `fundTransferId` prop -
  its `entityParams` map does the rest), with the existing eager
  count badge. `readOnly` on a cancelled row, and
  `canDelete={isSuperAdmin || !r.is_verified}` to mirror the server rule.

Tested against the live API: upload as both Super Admin and Admin, listing
scoped to the right transfer (a second transfer sees none), download
returning byte-identical content, the stored path confirmed to use a
per-transfer folder and a uuid filename (never the original), disallowed
extension / no-entity-id / unknown-transfer-id all 400,
accounts+manager+superaccounts 403 on upload/list/download/delete, Admin
delete allowed while unverified then 403 once verified, Admin still able
to view and add after verification, Super Admin delete working, and the
Document row actually removed. Plus a documents regression on the
pre-existing paths (expense attachment upload/list/download/delete, and
**Accounts still having its normal document access** - checking the new
guard isn''t over-broad).

## Shared `TruncatedText` cell + one-line table rows (done)
`components/ui.jsx` gained **`TruncatedText`** - a reusable one-line cell
for arbitrarily long free text (remarks, notes, references). It clamps to
a `width` prop with a CSS ellipsis, and **only when the text actually
overflows** (`scrollWidth > clientWidth`) opens a floating card on hover
with the full value: `whitespace-pre-wrap`, `select-text` so it can be
selected, scrollable past ~15 lines, and a Copy button
(`navigator.clipboard`, with the selectable text as the fallback when the
clipboard is blocked).

Implementation details that matter (the usual browser-only traps):
- The card is rendered through `createPortal` into `document.body` with
  `position: fixed`, **not** absolutely inside the cell - every table in
  this app sits in an `overflow-x-auto` wrapper that would clip it.
- It stays open while the pointer is over either the cell or the card
  (150ms close delay), so the text can actually be reached and selected
  instead of vanishing on the way there.
- Position is clamped horizontally to the viewport and flips above the
  cell when there is under 180px of room below.
- Any scroll or resize closes it, since the position was captured from a
  one-off `getBoundingClientRect` - **except** a scroll originating inside
  the card itself (checked with `cardRef.current.contains(e.target)`),
  which is exactly what reading a long value needs. Caught while
  reviewing, not after the fact.

`Table` gained an **`oneLine`** prop that applies `whitespace-nowrap` to
every cell, so each row is exactly one line tall. Default is `false`, so
no existing table changed. Pair it with `TruncatedText` on the free-text
columns - `oneLine` alone would just let long values widen the table.

Applied in `pages/Funds.jsx`: the Transfers & Funding table is `oneLine`
with `TruncatedText` on From / To / Ref / Remarks (including the
"Cancelled: <reason>" variant, which keeps its danger styling), and the
Funding Entities table is `oneLine` with it on Notes. Verified with
`npm run build` and `npm run lint` (21 pre-existing warnings, none in the
touched files, zero errors). No backend change.

## Funds: Super Admin verification lock on transfers (done)
A fund transfer can be **verified** by Super Admin, which locks it. Follows
the existing `is_verified` / `verified_by` / `verified_at` +
verify/unverify-endpoint convention already used by Expense, Payment,
Invoice and RecurringExpense - but with a *stricter* role rule, because
here the point is to lock Admin out, not Accounts:

- `POST /funds/transfers/{id}/verify` - **`require_super_admin`** (note:
  the rest of the module is `require_admin`; these two endpoints are the
  only Super-Admin-only ones). 400 on an already-verified or cancelled row.
- `POST /funds/transfers/{id}/unverify` - Super Admin, body `{reason}`
  (required). Clears the verifier and re-opens the row to Admin.
- Once verified, `_guard_verified()` gates both `PUT /funds/transfers/{id}`
  and `POST .../cancel`: non-Super-Admin gets **403**, Super Admin without
  a reason gets **400**. Cancel is gated on the same terms deliberately -
  otherwise Admin could bypass the lock with cancel-and-re-enter.
- `TransferIn.edit_reason` carries the reason on edit; it is stored on the
  row as `last_edit_reason` (new column, latest only) and written into the
  audit entry as `{"verified_at_edit": true, "edit_reason": "..."}`
  alongside the usual before/after - the audit log is the full history,
  the column is just for display.
- Editing a verified row keeps it verified (it does not silently reset to
  unverified). Verification state has no effect on any money figure.
- New columns on `fund_transfers`: `is_verified`, `verified_by`,
  `verified_at`, `last_edit_reason` - all additive, so `migrate.py` picked
  them up on restart (confirmed against the live DB).
- `GET /funds/transfers` gained a `verified=true|false` filter.

Frontend (`pages/Funds.jsx`): a Verified column showing the verifier's name
(tooltip carries verified-by/at and the last edit reason), a shield
Verify/Un-verify button shown only to Super Admin, Edit/Cancel buttons
hidden on a verified row for anyone who isn't Super Admin (`canModify`),
and an amber "this entry is verified - a reason is required" panel with a
mandatory reason textarea inside the edit form. Frontend gating is UX only;
the server is the boundary.

Tested against the live API (22 assertions): new rows start unverified;
admin/accounts/manager/superaccounts all 403 on verify; unverified rows
stay freely editable by Admin with no reason; Super Admin verify records
the verifier; double-verify 400; verified row blocks Admin edit (even
*with* a reason supplied) and Admin cancel; Super Admin edit without a
reason 400 and with a whitespace-only reason 400, with the row provably
unchanged after both; Super Admin edit with a reason applies, stays
verified and stores the reason; Super Admin cancel of a verified row with
a reason; cancelled row can't be verified; unverify clears the verifier
and restores Admin's plain edit; double-unverify and reason-less unverify
400; Admin can't unverify; the `verified` filter partitions the list; and
the balance sheet is unaffected by verification. Audit rows for VERIFY /
UNVERIFY / CANCEL / UPDATE all confirmed in the DB, including the reason
on the verified edit.

## Funds: now Admin + Super Admin (done)
The Funds module was initially Super Admin only. It is now **Admin and
Super Admin**, which is just `require_admin` - the single module-level
router dependency in `routers/funds.py` plus the per-endpoint `Depends`
were swapped from `require_super_admin`, so there is no separate
read-vs-write split: Admin gets the whole module (entities, fund
accounts, transfers/funding/repayments, edit, cancel, balance sheet),
identically to Super Admin.

Frontend gating moved in step: the "Funds" nav section in
`MainLayout.jsx` and the `/funds` route guard in `App.jsx` are both
`["ADMIN", "SUPER_ADMIN"]` now - same role set as Masters.

ACCOUNTS, SUPER_ACCOUNTS, MANAGER, EMPLOYEE and VIEWER still have **no**
access to any funds endpoint (403). Worth noting the deliberate asymmetry:
Accounts does all the transactional work but fund tracking is a
management view, so Accounts is excluded here even though it can see the
financial dashboard. Tested with a real Admin login across every
endpoint - full write cycle (create/edit entity, create/edit account,
funding in, repayment out, transfer, edit transfer, cancel transfer),
validation guard rails still enforced for Admin, cancelled-row edit still
400, Admin's balance sheet byte-identical to Super Admin's, and
accounts/manager/superaccounts confirmed 403 on all four GETs plus the
create endpoint.

## Funds: edit an existing transfer / funding entry (done)
`PUT /funds/transfers/{id}` (Super Admin, like the rest of the module) -
full-payload replace reusing the same `TransferIn` body as create.

- Validation is shared, not duplicated: `_resolve_transfer(db, payload)`
  does every check and resolves `(funding_entity_id, funding_type)`;
  `_apply_transfer(row, payload, ...)` writes the result onto the row,
  nulling whichever account side the kind doesn't use. Both create and
  update call the pair, so the two paths can't drift apart in what they
  accept (same reasoning as `edit_request_service.apply_changes`).
- **The kind is editable**, including switching between all three. Flipping
  FUNDING -> REPAYMENT moves the account from `to_` to `from_`; switching
  to TRANSFER clears `funding_entity_id`/`funding_type` outright. The
  balance sheet just recomputes from the rows, so no cached figure needs
  invalidating.
- `transfer_number` is immutable (never taken from the payload).
- A **cancelled** transfer cannot be edited (400) - it's history; record a
  fresh entry instead.
- Every edit writes an `AuditLog` UPDATE row holding
  `{"before": {...}, "after": {...}}` snapshots of all the business fields.

Frontend: `TransferForm` in `pages/Funds.jsx` took an optional `existing`
prop - same form for both modes, prefilled from the row and submitting
PUT instead of POST. A pencil Edit button sits next to the existing
Cancel button on each non-cancelled row.

Tested against the live API: field edits with the number unchanged,
funding-entity reassignment, both kind switches (with the account sides
and funding fields correctly rewritten), all seven create-side guard
rails rejected identically on edit, the row provably untouched after a
rejected edit, unknown id 404, cancelled row 400, balance-sheet totals
following a kind flip (net_funded going to -80000), audit before/after
rows present in the DB, and admin/accounts/manager all 403.

**Test-hygiene note**: the funds tests create entities/accounts/transfers
in the live `data/expms.db`. Delete those rows by explicit id afterwards -
do not bulk `delete from fund_transfers`, and never delete from
`audit_logs` (append-only by design; a few test FUND_TRANSFER entries
there are harmless).
