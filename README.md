# Expense & Payment Management System

A production-oriented web app for daily expense entry, supplier invoices,
employee claims, document uploads, payments, payment allocation, approvals,
audit trails, and management reporting — built from the attached development
plan.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic v2, JWT auth
- **Database:** SQLite (file-based, zero setup — schema is written to be
  PostgreSQL-compatible if you outgrow it later)
- **Frontend:** React 18 + Vite 5 + React Router 6 + Axios, Tailwind CSS 3.4

## What's implemented

Everything in the development plan's Phases 1–8:

- Unified expense engine — supplier invoices, direct expenses, and employee
  claims all resolve into a single `expenses` table, with unpaid/partial/paid
  states calculated **only** from payment allocations (never set directly)
- Multiple payments per expense, one payment split across multiple expenses,
  and an over-allocation guard that rejects any allocation exceeding the
  outstanding balance
- "Pay Immediately" / "Save & Pay" — expense + payment + allocation created
  atomically in one DB transaction
- Employee claim lifecycle: Draft → Submit → Approve/Reject → Resubmit, where
  approval atomically creates one expense per claim line
- Document upload with MIME/extension/size validation, server-generated
  filenames, and authenticated download-only access
- Role-based access (Employee / Manager / Accounts / Admin / Viewer),
  configurable approval rules (no hard-coded thresholds)
- Immutable audit log on every create/update/cancel/submit/approve/reject/pay
  action; financial records are cancelled, never deleted
- Dashboard, daily register, vendor outstanding, employee-wise and
  project-wise reports

All of the plan's "Mandatory Test Scenarios" (§30) were run against the
running API and pass, including the over-allocation rejection case.

## Running it

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install fastapi "uvicorn[standard]" sqlalchemy alembic "pydantic>=2" \
    pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" \
    python-multipart "bcrypt==4.0.1" email-validator

python -m app.seed          # creates expms.db, roles, and sample logins
uvicorn app.main:app --reload --port 8000
python3 -m uvicorn app.main:app --reload --port 8000 
```

The API is now at `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

Seeded logins (username / password):

| Role        | Username     | Password          |
|-------------|--------------|-------------------|
| Super Admin | `superadmin` | `SuperAdmin@123`  |
| Admin       | `admin`      | `Admin@123`       |
| Accounts    | `accounts`   | `Accounts@123`    |
| Manager     | `manager`    | `Manager@123`     |
| Employee    | `ajai`       | `Employee@123`    |

Super Admin is a superset of Admin everywhere Admin has access, plus two
exclusive powers: creating new roles, and resetting any user's password.
An ordinary Admin can create/disable users but cannot grant the Super Admin
role to anyone, cannot reset passwords, and cannot disable another Admin or
Super Admin account (guards against privilege escalation).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173` and talks to the API at the URL in `.env`
(`VITE_API_URL`, defaults to `http://localhost:8000`).

## Project layout

```
backend/
  app/
    core/        settings, JWT + password hashing, role-check dependencies
    models/      SQLAlchemy models (one table per plan §9) + enums
    schemas/     Pydantic request/response models
    services/    all financial business logic — expense/invoice/payment/
                 claim/approval-rule/audit/document/numbering/status
    routers/     FastAPI route handlers (thin — delegate to services)
    seed.py      idempotent seed script
    migrate.py   auto-migration script (see below)
    main.py      app entrypoint
frontend/
  src/
    api/         axios client with auth interceptor
    context/     auth context (JWT storage, current user)
    layouts/     sidebar shell matching the plan's navigation (§22)
    pages/       Dashboard, Expenses, Invoices, Payments, Claims, Reports,
                 Masters, Audit Logs
    components/  shared UI primitives (cards, tables, status badges, forms)
```

## Schema changes / database migrations

There's no Alembic wired in (despite being listed as a dependency) — instead
`backend/app/migrate.py` diffs the live SQLite database against the current
models on every app startup and **additively** applies the difference:

- Creates any table that's new since the last run
- Adds any column that's new on an existing table

It never drops, renames, or retypes anything — those are ambiguous/unsafe
to automate on SQLite (would require a full table rebuild) and are left for
you to handle by hand if they come up.

**In normal use you don't need to do anything** — just restart the backend
(`uvicorn app.main:app`) after pulling model changes and it self-heals. For
a readable summary of exactly what changed, run it directly:

```bash
cd backend
python -m app.migrate
```

If a change genuinely needs a drop/rename/retype, or you'd rather start
clean, reset the dev database instead (destroys data):

```bash
rm -f expms.db && python -m app.seed
```

## Notes on following the plan's own instructions (§32)

The plan asks Claude Code not to build everything in one pass and to keep
phases functional before moving on. In practice here that meant: build the
full data model and service layer first (since every transaction type shares
it), verify the core financial rules against the plan's mandatory test
scenarios via the live API, *then* build the UI on top of a backend already
known to be correct. The next natural extensions — noted in the plan as
future modules — are GST/TDS, vendor ledger, bank reconciliation, and
trial balance/P&L, none of which require reshaping the schema already in
place.
