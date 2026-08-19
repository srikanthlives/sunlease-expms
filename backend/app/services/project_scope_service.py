"""Project-scoping helpers for the ACCOUNTS role.

Per this feature, ACCOUNTS is ALWAYS project-restricted (no implicit
company-wide fallback): an Accounts user only sees/acts on
expenses/invoices/payments/claims belonging to projects they've been
explicitly assigned to via `project_accounts_users`. SUPER_ADMIN, ADMIN and
VIEWER are unaffected - this module is only ever consulted for role
ACCOUNTS specifically; callers should check `user.role.name == "ACCOUNTS"`
before using it (company-wide roles should skip scoping entirely).
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import Expense, Payment, PaymentAllocation, ProjectAccountsUser, User


def get_accounts_assigned_project_ids(db: Session, user: User) -> list[int]:
    """All project ids this ACCOUNTS user is assigned to. Empty list means
    zero scope (they should see nothing until an Admin assigns them)."""
    rows = db.query(ProjectAccountsUser.project_id).filter(ProjectAccountsUser.user_id == user.id).all()
    return [r[0] for r in rows]


def get_effective_project_scope(db: Session, user: User) -> list[int] | None:
    """`None` means unrestricted - the caller may show company-wide data
    unfiltered (any role other than ACCOUNTS). A list (possibly empty) means
    the caller MUST restrict to those project ids, e.g. via
    `Model.project_id.in_(ids)` (an empty list correctly yields zero rows via
    an empty IN clause). Used by dashboard/report endpoints so an ACCOUNTS
    user can never see aggregate/company-wide figures outside their assigned
    projects, even when no explicit project_id filter is passed."""
    if user.role.name != "ACCOUNTS":
        return None
    return get_accounts_assigned_project_ids(db, user)


def assert_project_in_scope(db: Session, user: User, project_id: int | None):
    """Raise 403 if this ACCOUNTS user is not assigned to project_id (or has
    no project assignments at all). A None project_id (an entity with no
    project set) is out of scope too - there's nothing to match against."""
    if project_id is not None:
        assigned = get_accounts_assigned_project_ids(db, user)
        if project_id in assigned:
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")


def payment_project_ids(db: Session, payment: Payment) -> list[int]:
    """Project ids touched by any of this payment's allocations (Payment has
    no project_id column of its own - reached via
    PaymentAllocation -> Expense.project_id, same join pattern used
    elsewhere in this codebase for project-scoped payment sums)."""
    rows = (
        db.query(Expense.project_id)
        .join(PaymentAllocation, PaymentAllocation.expense_id == Expense.id)
        .filter(PaymentAllocation.payment_id == payment.id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def assert_payment_in_scope(db: Session, user: User, payment: Payment):
    """A payment is in scope for an ACCOUNTS user if ANY of its allocations
    touch an expense in one of their assigned projects."""
    assigned = set(get_accounts_assigned_project_ids(db, user))
    touched = set(payment_project_ids(db, payment))
    if not (assigned & touched):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this payment's project(s)")
