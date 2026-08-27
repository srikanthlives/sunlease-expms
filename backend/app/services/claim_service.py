import datetime as dt
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import EmployeeClaim, EmployeeClaimLine, Document, User
from app.models.enums import ClaimStatus, SourceType, AuditAction, RoleName
from app.services import numbering, audit_service, expense_service, project_scope_service
from app.services.storage import get_storage


def create_draft_claim(db: Session, *, employee_id: int, project_id, category_id, description, lines: list[dict], created_by: int) -> EmployeeClaim:
    claim = EmployeeClaim(
        claim_number=numbering.next_claim_number(db),
        employee_id=employee_id,
        claim_date=dt.date.today(),
        project_id=project_id,
        category_id=category_id,
        description=description,
        total_amount=Decimal("0"),
        status=ClaimStatus.DRAFT,
    )
    db.add(claim)
    db.flush()
    _replace_lines(db, claim, lines)
    audit_service.record(db, "CLAIM", claim.id, AuditAction.CREATE, created_by, {"line_count": len(lines)})
    return claim


def update_draft_claim(db: Session, claim: EmployeeClaim, *, project_id, category_id, description, lines: list[dict], actor_id: int):
    if claim.status not in (ClaimStatus.DRAFT, ClaimStatus.REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only draft or rejected claims can be edited")
    claim.project_id = project_id
    claim.category_id = category_id
    claim.description = description
    _replace_lines(db, claim, lines)
    audit_service.record(db, "CLAIM", claim.id, AuditAction.UPDATE, actor_id, {"line_count": len(lines)})
    return claim


def delete_claim(db: Session, claim: EmployeeClaim, actor_id: int):
    """Employees may throw away a claim entirely while it's still theirs to
    change - same window as edit (DRAFT or REJECTED). Once submitted it's
    in someone else's hands and can no longer be pulled back this way. Hard
    delete (not the CANCELLED-status pattern used for financial records) is
    correct here since no Expense has been created yet at this stage - there
    is nothing downstream to preserve an audit trail against."""
    if claim.status not in (ClaimStatus.DRAFT, ClaimStatus.REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only draft or rejected claims can be deleted")
    line_ids = [line.id for line in claim.lines]
    docs = db.query(Document).filter(
        (Document.claim_id == claim.id) | (Document.claim_line_id.in_(line_ids) if line_ids else False)
    ).all()
    storage = get_storage()
    for doc in docs:
        storage.delete_file(doc.stored_filename)
        db.delete(doc)
    audit_service.record(db, "CLAIM", claim.id, AuditAction.DELETE, actor_id, {"claim_number": claim.claim_number})
    db.delete(claim)


def _replace_lines(db: Session, claim: EmployeeClaim, lines: list[dict]):
    """Reconciles claim.lines against the incoming line list in place, by
    id, instead of clearing and recreating every row on every edit. Each
    EmployeeClaimLine.id is the target of Document.claim_line_id (per-line
    attachment proof) - blindly deleting and recreating every line (even
    ones the user didn't touch, e.g. when only adding a new line) silently
    orphaned every existing attachment because the old line ids ceased to
    exist. Lines the caller genuinely removed still get deleted, along with
    their attachments (files included), same as delete_claim."""
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A claim requires at least one expense line")

    existing_by_id = {line.id: line for line in claim.lines}
    incoming_ids = {line["id"] for line in lines if line.get("id")}

    removed_ids = set(existing_by_id) - incoming_ids
    if removed_ids:
        docs = db.query(Document).filter(Document.claim_line_id.in_(removed_ids)).all()
        storage = get_storage()
        for doc in docs:
            storage.delete_file(doc.stored_filename)
            db.delete(doc)
        db.flush()

    for line in list(claim.lines):
        if line.id in removed_ids:
            claim.lines.remove(line)

    total = Decimal("0")
    for line in lines:
        amount = Decimal(str(line["amount"]))
        if amount <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each claim line amount must be greater than zero")
        line_id = line.get("id")
        existing = existing_by_id.get(line_id) if line_id else None
        if existing is not None:
            existing.expense_date = line["expense_date"]
            existing.expense_head_id = line["expense_head_id"]
            existing.expense_sub_head_id = line.get("expense_sub_head_id")
            existing.description = line.get("description")
            existing.amount = amount
            db.add(existing)
        else:
            claim.lines.append(EmployeeClaimLine(
                expense_date=line["expense_date"],
                expense_head_id=line["expense_head_id"],
                expense_sub_head_id=line.get("expense_sub_head_id"),
                description=line.get("description"),
                amount=amount,
            ))
        total += amount
    claim.total_amount = total
    db.flush()


def submit_claim(db: Session, claim: EmployeeClaim, actor_id: int) -> EmployeeClaim:
    if claim.status not in (ClaimStatus.DRAFT, ClaimStatus.REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only draft or rejected claims can be submitted")
    if not claim.lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot submit a claim with no expense lines")

    # Per business rule: the submission date becomes the accounting expense date.
    claim.claim_date = dt.date.today()
    claim.status = ClaimStatus.SUBMITTED
    claim.submitted_at = dt.datetime.utcnow()
    claim.rejected_at = None
    claim.rejection_reason = None
    db.add(claim)
    audit_service.record(db, "CLAIM", claim.id, AuditAction.SUBMIT, actor_id, {"total_amount": str(claim.total_amount)})
    return claim


def _authorize_manager_approval(claim: EmployeeClaim, actor: User):
    """Level 1: only the claim's employee's direct manager - or Admin/Super
    Admin as an oversight bypass - may act at this stage."""
    if actor.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        return
    if actor.role.name != RoleName.MANAGER or not actor.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this employee's manager can act on this claim")
    if claim.employee.manager_id != actor.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not this employee's manager")


def _authorize_accounts_approval(db: Session, claim: EmployeeClaim, actor: User):
    """Level 2: only the Accounts user assigned to the claim's project - or
    Admin/Super Admin - may act. A project with no assigned approver falls
    back to any Accounts user *assigned to that project* via
    project_accounts_users (not literally any Accounts user - see
    project-scoping feature). A claim with no project at all keeps the
    original any-Accounts-user fallback, since there's no project to scope by."""
    if actor.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        return
    if actor.role.name != RoleName.ACCOUNTS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Accounts can give final approval on this claim")
    project = claim.project
    if project is None:
        return
    if project.accounts_approver_id:
        if project.accounts_approver_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not the assigned approver for this project")
        return
    assigned = project_scope_service.get_accounts_assigned_project_ids(db, actor)
    if project.id not in assigned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this project")


def approve_claim(db: Session, claim: EmployeeClaim, actor: User, remarks: str | None = None) -> EmployeeClaim:
    """Two-level approval:
    - SUBMITTED -> manager approves -> PENDING_ACCOUNTS_APPROVAL
    - PENDING_ACCOUNTS_APPROVAL -> accounts approves -> APPROVED (creates ONE
      consolidated Expense for the whole claim, atomically - not one per
      line. All lines still point to that same expense_id for traceability,
      and the claim itself carries expense_id/expense_number too.)
    """
    if claim.status == ClaimStatus.SUBMITTED:
        _authorize_manager_approval(claim, actor)
        claim.status = ClaimStatus.PENDING_ACCOUNTS_APPROVAL
        db.add(claim)
        audit_service.record(db, "CLAIM", claim.id, AuditAction.APPROVE, actor.id, {"level": "MANAGER", "remarks": remarks})
        return claim

    if claim.status == ClaimStatus.PENDING_ACCOUNTS_APPROVAL:
        _authorize_accounts_approval(db, claim, actor)
        if not claim.lines:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claim has no lines to approve")

        recalculated_total = sum(Decimal(line.amount) for line in claim.lines)
        if recalculated_total != Decimal(claim.total_amount):
            claim.total_amount = recalculated_total

        # The claim's overall Expense Head (chosen at claim creation) drives
        # the consolidated expense's category directly - it's what the
        # employee/claim represents as a whole, not an inference over lines.
        # Sub-category still only carries through when every line agrees,
        # since there's no claim-level "overall sub-head" concept.
        sub_head_ids = {line.expense_sub_head_id for line in claim.lines if line.expense_sub_head_id}
        category_id = claim.category_id
        sub_category_id = sub_head_ids.pop() if len(sub_head_ids) == 1 else None

        line_descriptions = [line.description for line in claim.lines if line.description]
        summary = "; ".join(line_descriptions) if line_descriptions else f"{len(claim.lines)} item(s)"
        description = f"{claim.description} — {summary}" if claim.description else summary

        expense = expense_service.create_expense_record(
            db, source_type=SourceType.EMPLOYEE_CLAIM, source_id=claim.id, expense_date=claim.claim_date,
            project_id=claim.project_id, vendor_id=None, employee_id=claim.employee_id,
            category_id=category_id, sub_category_id=sub_category_id,
            description=description, base_amount=claim.total_amount, gst_amount=0, other_amount=0,
            created_by=actor.id,
        )
        claim.expense_id = expense.id
        for line in claim.lines:
            line.expense_id = expense.id
            db.add(line)

        claim.status = ClaimStatus.APPROVED
        claim.approved_at = dt.datetime.utcnow()
        claim.approved_by = actor.id
        db.add(claim)
        audit_service.record(db, "CLAIM", claim.id, AuditAction.APPROVE, actor.id, {"level": "ACCOUNTS", "remarks": remarks, "expense_id": expense.id, "line_count": len(claim.lines)})
        return claim

    raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim is not awaiting approval")


def reject_claim(db: Session, claim: EmployeeClaim, actor: User, reason: str) -> EmployeeClaim:
    if not reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A rejection reason is required")

    if claim.status == ClaimStatus.SUBMITTED:
        _authorize_manager_approval(claim, actor)
        level = "MANAGER"
    elif claim.status == ClaimStatus.PENDING_ACCOUNTS_APPROVAL:
        _authorize_accounts_approval(db, claim, actor)
        level = "ACCOUNTS"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim is not awaiting approval")

    claim.status = ClaimStatus.REJECTED
    claim.rejected_at = dt.datetime.utcnow()
    claim.rejection_reason = reason
    db.add(claim)
    audit_service.record(db, "CLAIM", claim.id, AuditAction.REJECT, actor.id, {"level": level, "reason": reason})
    return claim
