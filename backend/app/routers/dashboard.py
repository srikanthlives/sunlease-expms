import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.enums import RoleName
from app.models.models import Expense, Payment, EmployeeClaim, Vendor, Employee, Project, User, PaymentAllocation
from app.services.payment_status_service import get_paid_amount
from app.services import project_scope_service

router = APIRouter(prefix="/api/v1", tags=["dashboard-reports"])

# Company-wide financial dashboard/reports are for Admin/Super Admin/Accounts/
# Viewer only. Employees see /dashboard/my-claims; Managers see
# /dashboard/approvals - neither has a reason to see company-wide totals.
require_report_viewer = require_roles(RoleName.SUPER_ADMIN, RoleName.ADMIN, RoleName.ACCOUNTS, RoleName.VIEWER)


def _d(v):
    return float(v or 0)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user), project_id: int | None = None):
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN, RoleName.ACCOUNTS, RoleName.VIEWER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account uses a role-specific dashboard instead")

    project = None
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    # ACCOUNTS is always project-restricted: if a project_id was given it must
    # be one of their assigned projects; if not, every aggregate below gets
    # implicitly constrained to their assigned set instead of company-wide.
    scope = project_scope_service.get_effective_project_scope(db, user)
    if project_id and scope is not None and project_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")

    # effective_ids: None = unrestricted (company-wide). A list (possibly
    # empty) = restrict every query below to exactly these project ids.
    effective_ids: list[int] | None
    if project_id:
        effective_ids = [project_id]
    else:
        effective_ids = scope

    today = dt.date.today()
    month_start = today.replace(day=1)

    def scope_filter(column):
        return [column.in_(effective_ids)] if effective_ids is not None else []

    def expense_q(*filters):
        q = db.query(Expense).filter(Expense.status == "ACTIVE", *filters)
        q = q.filter(*scope_filter(Expense.project_id))
        return q

    def payment_sum(start=None, end=None, single_day=None):
        """Payments don't carry project_id directly - when scoped to project(s),
        sum via the allocation -> expense join instead of the payment table
        directly."""
        if effective_ids is None:
            q = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.is_cancelled.is_(False))
            if single_day:
                q = q.filter(Payment.payment_date == single_day)
            else:
                q = q.filter(Payment.payment_date >= start, Payment.payment_date < end)
            return _d(q.scalar())
        q = (
            db.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
            .join(Payment, PaymentAllocation.payment_id == Payment.id)
            .join(Expense, PaymentAllocation.expense_id == Expense.id)
            .filter(Payment.is_cancelled.is_(False), Expense.project_id.in_(effective_ids))
        )
        if single_day:
            q = q.filter(Payment.payment_date == single_day)
        else:
            q = q.filter(Payment.payment_date >= start, Payment.payment_date < end)
        return _d(q.scalar())

    todays_expenses = _d(db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
        Expense.expense_date == today, Expense.status == "ACTIVE", *scope_filter(Expense.project_id)).scalar())
    todays_payments = payment_sum(single_day=today)
    month_expenses = _d(db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
        Expense.expense_date >= month_start, Expense.status == "ACTIVE", *scope_filter(Expense.project_id)).scalar())
    outstanding = _d(db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
        Expense.status == "ACTIVE", Expense.payment_status != "PAID", *scope_filter(Expense.project_id)).scalar())

    pending_claims_q = db.query(func.count(EmployeeClaim.id)).filter(EmployeeClaim.status.in_(["SUBMITTED", "PENDING_ACCOUNTS_APPROVAL"]))
    pending_claims_q = pending_claims_q.filter(*scope_filter(EmployeeClaim.project_id))
    pending_claims = pending_claims_q.scalar()

    by_category_q = db.query(Expense.category_id, func.sum(Expense.total_amount)).filter(Expense.status == "ACTIVE", Expense.expense_date >= month_start)
    by_category_q = by_category_q.filter(*scope_filter(Expense.project_id))
    by_category = by_category_q.group_by(Expense.category_id).all()

    by_project = []
    if not project_id:
        by_project_q = db.query(Expense.project_id, func.sum(Expense.total_amount)).filter(
            Expense.status == "ACTIVE", Expense.expense_date >= month_start)
        # Even in the multi-project (no single project_id) case, an ACCOUNTS
        # user's breakdown must never list a project outside their scope.
        by_project_q = by_project_q.filter(*scope_filter(Expense.project_id))
        by_project = by_project_q.group_by(Expense.project_id).all()

    months = []
    for i in range(5, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    trend = []
    for (y, m) in months:
        start = dt.date(y, m, 1)
        end = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        exp = _d(db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
            Expense.expense_date >= start, Expense.expense_date < end, Expense.status == "ACTIVE",
            *scope_filter(Expense.project_id)).scalar())
        pay = payment_sum(start=start, end=end)
        trend.append({"month": f"{y}-{m:02d}", "expenses": exp, "payments": pay})

    result = {
        "project_id": project_id,
        "todays_expenses": todays_expenses,
        "todays_payments": todays_payments,
        "month_expenses": month_expenses,
        "outstanding": outstanding,
        "pending_claims": pending_claims,
        "pending_approvals": pending_claims,
        "expense_by_category": [{"category_id": c, "amount": _d(a)} for c, a in by_category],
        "expense_by_project": [{"project_id": p, "amount": _d(a)} for p, a in by_project],
        "monthly_trend": trend,
    }

    if project:
        approver = project.accounts_approver
        all_expenses = expense_q().all()
        all_time_expense = sum(Decimal(e.total_amount) for e in all_expenses)
        all_time_paid = sum(get_paid_amount(db, e.id) for e in all_expenses)
        result["project"] = {
            "id": project.id, "code": project.code, "name": project.name, "description": project.description,
            "accounts_approver_name": (approver.full_name or approver.username) if approver else None,
            "all_time_expense": _d(all_time_expense),
            "all_time_paid": _d(all_time_paid),
            "all_time_outstanding": _d(all_time_expense - all_time_paid),
        }

    return result


@router.get("/reports/daily-register", dependencies=[Depends(require_report_viewer)])
def daily_register(date: str = Query(default=None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = dt.date.fromisoformat(date) if date else dt.date.today()
    scope = project_scope_service.get_effective_project_scope(db, user)

    def sum_expense(source_type):
        q = db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
            Expense.expense_date == target, Expense.source_type == source_type, Expense.status == "ACTIVE")
        if scope is not None:
            q = q.filter(Expense.project_id.in_(scope))
        return _d(q.scalar())

    invoices = sum_expense("INVOICE")
    direct = sum_expense("DIRECT_EXPENSE")
    claims = sum_expense("EMPLOYEE_CLAIM")

    def payment_sum_by_party(party_column):
        if scope is None:
            q = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                Payment.payment_date == target, party_column.isnot(None), Payment.is_cancelled.is_(False))
            return _d(q.scalar())
        # Payments carry no project_id directly - scope via their allocations' expenses.
        q = (
            db.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
            .join(Payment, PaymentAllocation.payment_id == Payment.id)
            .join(Expense, PaymentAllocation.expense_id == Expense.id)
            .filter(Payment.payment_date == target, party_column.isnot(None), Payment.is_cancelled.is_(False), Expense.project_id.in_(scope))
        )
        return _d(q.scalar())

    vendor_payments = payment_sum_by_party(Payment.vendor_id)
    employee_payments = payment_sum_by_party(Payment.employee_id)

    return {
        "date": str(target),
        "expenses": {"invoices": invoices, "direct_expenses": direct, "employee_claims": claims, "total": invoices + direct + claims},
        "payments": {"vendor_payments": vendor_payments, "employee_payments": employee_payments, "total": vendor_payments + employee_payments},
    }


@router.get("/reports/vendor-outstanding", dependencies=[Depends(require_report_viewer)])
def vendor_outstanding(db: Session = Depends(get_db), user: User = Depends(get_current_user), project_id: int | None = None, date_from: str | None = None, date_to: str | None = None):
    scope = project_scope_service.get_effective_project_scope(db, user)
    if project_id and scope is not None and project_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")
    vendors = db.query(Vendor).all()
    result = []
    for v in vendors:
        q = db.query(Expense).filter(Expense.vendor_id == v.id, Expense.status == "ACTIVE")
        if project_id:
            q = q.filter(Expense.project_id == project_id)
        elif scope is not None:
            q = q.filter(Expense.project_id.in_(scope))
        if date_from:
            q = q.filter(Expense.expense_date >= date_from)
        if date_to:
            q = q.filter(Expense.expense_date <= date_to)
        expenses = q.all()
        invoiced = sum(Decimal(e.total_amount) for e in expenses)
        if invoiced <= 0:
            continue
        actual_paid = sum(get_paid_amount(db, e.id) for e in expenses)
        vendor_name = f"{v.vendor_name} ({v.location})" if v.location else v.vendor_name
        result.append({
            "vendor_id": v.id, "vendor_name": vendor_name,
            "invoiced": _d(invoiced), "paid": _d(actual_paid), "outstanding": _d(invoiced - actual_paid),
        })
    return result


@router.get("/reports/employee-wise", dependencies=[Depends(require_report_viewer)])
def employee_wise_report(db: Session = Depends(get_db), user: User = Depends(get_current_user), project_id: int | None = None, date_from: str | None = None, date_to: str | None = None):
    scope = project_scope_service.get_effective_project_scope(db, user)
    if project_id and scope is not None and project_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")
    employees = db.query(Employee).all()
    result = []
    for emp in employees:
        claims_q = db.query(EmployeeClaim).filter(EmployeeClaim.employee_id == emp.id)
        if project_id:
            claims_q = claims_q.filter(EmployeeClaim.project_id == project_id)
        elif scope is not None:
            claims_q = claims_q.filter(EmployeeClaim.project_id.in_(scope))
        if date_from:
            claims_q = claims_q.filter(EmployeeClaim.claim_date >= date_from)
        if date_to:
            claims_q = claims_q.filter(EmployeeClaim.claim_date <= date_to)
        claims = claims_q.all()
        if not claims:
            continue
        claimed = sum(Decimal(c.total_amount) for c in claims)
        approved = sum(Decimal(c.total_amount) for c in claims if c.status == "APPROVED")

        exp_q = db.query(Expense).filter(Expense.employee_id == emp.id, Expense.status == "ACTIVE")
        if project_id:
            exp_q = exp_q.filter(Expense.project_id == project_id)
        elif scope is not None:
            exp_q = exp_q.filter(Expense.project_id.in_(scope))
        if date_from:
            exp_q = exp_q.filter(Expense.expense_date >= date_from)
        if date_to:
            exp_q = exp_q.filter(Expense.expense_date <= date_to)
        expenses = exp_q.all()
        paid = sum(get_paid_amount(db, e.id) for e in expenses)
        total_expense = sum(Decimal(e.total_amount) for e in expenses)
        result.append({
            "employee_id": emp.id, "employee_name": emp.employee_name, "total_claims": len(claims),
            "claimed": _d(claimed), "approved": _d(approved), "paid": _d(paid), "outstanding": _d(total_expense - paid),
        })
    return result


@router.get("/reports/project-wise", dependencies=[Depends(require_report_viewer)])
def project_wise_report(db: Session = Depends(get_db), user: User = Depends(get_current_user), date_from: str | None = None, date_to: str | None = None):
    scope = project_scope_service.get_effective_project_scope(db, user)
    projects_q = db.query(Project)
    if scope is not None:
        projects_q = projects_q.filter(Project.id.in_(scope))
    projects = projects_q.all()
    result = []
    for proj in projects:
        q = db.query(Expense).filter(Expense.project_id == proj.id, Expense.status == "ACTIVE")
        if date_from:
            q = q.filter(Expense.expense_date >= date_from)
        if date_to:
            q = q.filter(Expense.expense_date <= date_to)
        expenses = q.all()
        invoices = sum(Decimal(e.total_amount) for e in expenses if e.source_type == "INVOICE")
        direct = sum(Decimal(e.total_amount) for e in expenses if e.source_type == "DIRECT_EXPENSE")
        claims = sum(Decimal(e.total_amount) for e in expenses if e.source_type == "EMPLOYEE_CLAIM")
        total = invoices + direct + claims
        paid = sum(get_paid_amount(db, e.id) for e in expenses)
        result.append({
            "project_id": proj.id, "project_name": proj.name, "invoices": _d(invoices), "direct_expenses": _d(direct),
            "employee_claims": _d(claims), "total_expense": _d(total), "payments": _d(paid), "outstanding": _d(total - paid),
        })
    return result


@router.get("/reports/date-bounds", dependencies=[Depends(require_report_viewer)])
def date_bounds(db: Session = Depends(get_db)):
    """Earliest and latest expense_date with recorded activity, so the
    frontend can offer a sensible default range (and clamp presets like
    'All Time') without guessing."""
    earliest = db.query(func.min(Expense.expense_date)).filter(Expense.status == "ACTIVE").scalar()
    latest = db.query(func.max(Expense.expense_date)).filter(Expense.status == "ACTIVE").scalar()
    today = dt.date.today()
    return {
        "earliest": str(earliest) if earliest else str(today),
        "latest": str(latest) if latest else str(today),
        "today": str(today),
    }


@router.get("/reports/trend", dependencies=[Depends(require_report_viewer)])
def trend_report(
    db: Session = Depends(get_db), user: User = Depends(get_current_user), project_id: int | None = None,
    date_from: str | None = None, date_to: str | None = None,
):
    """Month-bucketed expense/payment trend across an arbitrary date range -
    powers the Trend Report page's chart + table. Defaults to the last 6
    months up to today when no range is given. Each bucket is clipped to
    the requested range, so a range that starts or ends mid-month only
    counts the days actually inside it."""
    scope = project_scope_service.get_effective_project_scope(db, user)
    if project_id and scope is not None and project_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")
    effective_ids = [project_id] if project_id else scope
    today = dt.date.today()
    range_end = dt.date.fromisoformat(date_to) if date_to else today
    range_start = dt.date.fromisoformat(date_from) if date_from else (range_end.replace(day=1) - dt.timedelta(days=150)).replace(day=1)
    if range_start > range_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from must be on or before date_to")

    def month_bounds(y, m):
        start = dt.date(y, m, 1)
        end = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        return start, end

    buckets = []
    y, m = range_start.year, range_start.month
    while (y, m) <= (range_end.year, range_end.month):
        month_start, month_end = month_bounds(y, m)
        effective_start = max(month_start, range_start)
        effective_end = min(month_end, range_end + dt.timedelta(days=1))
        buckets.append({"year": y, "month": m, "start": effective_start, "end": effective_end})
        m += 1
        if m > 12:
            m = 1
            y += 1

    def expense_sum(start, end, source_type=None):
        q = db.query(func.coalesce(func.sum(Expense.total_amount), 0)).filter(
            Expense.expense_date >= start, Expense.expense_date < end, Expense.status == "ACTIVE")
        if source_type:
            q = q.filter(Expense.source_type == source_type)
        if effective_ids is not None:
            q = q.filter(Expense.project_id.in_(effective_ids))
        return _d(q.scalar())

    months = []
    for b in buckets:
        start, end = b["start"], b["end"]
        invoices = expense_sum(start, end, "INVOICE")
        direct = expense_sum(start, end, "DIRECT_EXPENSE")
        claims = expense_sum(start, end, "EMPLOYEE_CLAIM")
        total_expense = invoices + direct + claims

        pay_q = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.payment_date >= start, Payment.payment_date < end, Payment.is_cancelled.is_(False))
        if effective_ids is not None:
            # Payments don't carry project_id directly - scope via their allocations' expenses.
            pay_q = (
                db.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
                .join(Payment, PaymentAllocation.payment_id == Payment.id)
                .join(Expense, PaymentAllocation.expense_id == Expense.id)
                .filter(Payment.payment_date >= start, Payment.payment_date < end, Payment.is_cancelled.is_(False), Expense.project_id.in_(effective_ids))
            )
        payments = _d(pay_q.scalar())

        months.append({
            "year": b["year"], "month": b["month"], "label": f"{b['year']}-{b['month']:02d}",
            "invoices": invoices, "direct_expenses": direct, "employee_claims": claims,
            "total_expense": total_expense, "payments": payments, "outstanding": total_expense - payments,
        })

    return {
        "date_from": str(range_start), "date_to": str(range_end), "project_id": project_id, "months": months,
        "totals": {
            "total_expense": sum(m["total_expense"] for m in months),
            "payments": sum(m["payments"] for m in months),
            "invoices": sum(m["invoices"] for m in months),
            "direct_expenses": sum(m["direct_expenses"] for m in months),
            "employee_claims": sum(m["employee_claims"] for m in months),
        },
    }


@router.get("/dashboard/my-claims")
def my_claims_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Personal snapshot for anyone with an employee record (Employee or
    Manager): their own claim pipeline and reimbursement status, with no
    visibility into company-wide totals."""
    if not user.employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This account isn't linked to an employee record")

    claims = db.query(EmployeeClaim).filter(EmployeeClaim.employee_id == user.employee_id).all()
    by_status = {}
    for c in claims:
        by_status[c.status] = by_status.get(c.status, 0) + 1

    total_claimed = sum(Decimal(c.total_amount) for c in claims)
    total_approved = sum(Decimal(c.total_amount) for c in claims if c.status == "APPROVED")

    expenses = db.query(Expense).filter(Expense.employee_id == user.employee_id, Expense.status == "ACTIVE").all()
    total_paid = sum(get_paid_amount(db, e.id) for e in expenses)
    total_owed = sum(Decimal(e.total_amount) for e in expenses) - total_paid

    recent = sorted(claims, key=lambda c: c.id, reverse=True)[:5]

    return {
        "total_claims": len(claims),
        "by_status": by_status,
        "total_claimed": _d(total_claimed),
        "total_approved": _d(total_approved),
        "total_paid": _d(total_paid),
        "total_owed_to_me": _d(total_owed),
        "recent_claims": [
            {"id": c.id, "claim_number": c.claim_number, "claim_date": str(c.claim_date), "status": c.status, "total_amount": _d(c.total_amount)}
            for c in recent
        ],
    }


@router.get("/dashboard/approvals")
def approvals_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Level-1 approvals snapshot for a Manager: claims submitted by their
    *direct reports* only, awaiting their review. Admin/Super Admin get an
    org-wide view for oversight. Not available to Accounts (they have their
    own /dashboard/accounts-approvals) or Employee."""
    if user.role.name not in (RoleName.MANAGER, RoleName.ADMIN, RoleName.SUPER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Managers use this dashboard")

    q = db.query(EmployeeClaim).filter(EmployeeClaim.status == "SUBMITTED")
    if user.role.name == RoleName.MANAGER:
        if not user.employee_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This Manager account isn't linked to an employee record")
        q = q.join(Employee, EmployeeClaim.employee_id == Employee.id).filter(Employee.manager_id == user.employee_id)
    pending = q.order_by(EmployeeClaim.submitted_at).all()
    pending_total = sum(Decimal(c.total_amount) for c in pending)

    thirty_days_ago = dt.datetime.combine(dt.date.today() - dt.timedelta(days=30), dt.time.min)
    approved_q = db.query(EmployeeClaim).filter(EmployeeClaim.status.in_(["PENDING_ACCOUNTS_APPROVAL", "APPROVED"]))
    rejected_q = db.query(EmployeeClaim).filter(EmployeeClaim.status == "REJECTED", EmployeeClaim.rejected_at >= thirty_days_ago)
    if user.role.name == RoleName.MANAGER:
        approved_q = approved_q.join(Employee, EmployeeClaim.employee_id == Employee.id).filter(Employee.manager_id == user.employee_id)
        rejected_q = rejected_q.join(Employee, EmployeeClaim.employee_id == Employee.id).filter(Employee.manager_id == user.employee_id)

    return {
        "pending_count": len(pending),
        "pending_total": _d(pending_total),
        "recently_approved_30d": approved_q.count(),
        "recently_rejected_30d": rejected_q.count(),
        "pending_claims": [
            {"id": c.id, "claim_number": c.claim_number, "employee_id": c.employee_id, "total_amount": _d(c.total_amount), "submitted_at": str(c.submitted_at) if c.submitted_at else None}
            for c in pending[:8]
        ],
    }


@router.get("/dashboard/accounts-approvals", dependencies=[Depends(require_report_viewer)])
def accounts_approvals_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Level-2 approvals snapshot for Accounts: manager-approved claims
    awaiting final sign-off on projects assigned to this Accounts user (plus
    projects with no approver assigned, and claims with no project at all,
    as a fallback pool). Admin/Super Admin see everything."""
    q = db.query(EmployeeClaim).filter(EmployeeClaim.status == "PENDING_ACCOUNTS_APPROVAL")
    if user.role.name == RoleName.ACCOUNTS:
        q = (
            q.outerjoin(Project, EmployeeClaim.project_id == Project.id)
            .filter(or_(
                Project.accounts_approver_id == user.id,
                EmployeeClaim.project_id.is_(None),
                Project.accounts_approver_id.is_(None),
            ))
        )
    pending = q.order_by(EmployeeClaim.id).all()
    pending_total = sum(Decimal(c.total_amount) for c in pending)

    return {
        "pending_count": len(pending),
        "pending_total": _d(pending_total),
        "pending_claims": [
            {"id": c.id, "claim_number": c.claim_number, "employee_id": c.employee_id, "project_id": c.project_id, "total_amount": _d(c.total_amount)}
            for c in pending[:10]
        ],
    }
