from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.core.deps import get_current_user, require_approver
from app.db.session import get_db
from app.models.models import EmployeeClaim, Employee, Project, User
from app.models.enums import ClaimStatus, RoleName
from app.schemas.transactions import ClaimCreate, ClaimUpdate, ClaimOut, RejectRequest
from app.services import claim_service, project_scope_service, claim_pdf_service

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])


def _can_edit(claim: EmployeeClaim, user: User) -> bool:
    """Only the owning employee, or Admin/Super Admin, may edit/submit."""
    if user.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        return True
    return user.employee_id is not None and user.employee_id == claim.employee_id


def _can_view(db: Session, claim: EmployeeClaim, user: User) -> bool:
    role = user.role.name
    if role in (RoleName.SUPER_ADMIN, RoleName.ADMIN, RoleName.VIEWER):
        return True
    if role == RoleName.ACCOUNTS:
        # Project-scoped: visible if the claim has no project (fallback pool,
        # unchanged) or its project is one this Accounts user is assigned to.
        if claim.project_id is None:
            return True
        return claim.project_id in project_scope_service.get_accounts_assigned_project_ids(db, user)
    if user.employee_id == claim.employee_id:
        return True
    if role == RoleName.MANAGER and user.employee_id:
        employee = db.query(Employee).filter(Employee.id == claim.employee_id).first()
        return bool(employee and employee.manager_id == user.employee_id)
    return False


def _assert_claim_project_allowed(db: Session, user: User, employee_id: int, project_id: int | None):
    """An employee (or manager, submitting their own claim) can't tag a
    claim to a project they don't actually belong to - Admin/Super Admin
    may set any project. Only enforced when a project is actually given."""
    if user.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN) or project_id is None:
        return
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee or project_id not in employee.project_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can only submit claims against a project you belong to")


@router.post("", response_model=ClaimOut)
def create_claim(payload: ClaimCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN) and user.employee_id != payload.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only create claims for yourself")
    _assert_claim_project_allowed(db, user, payload.employee_id, payload.project_id)
    claim = claim_service.create_draft_claim(
        db, employee_id=payload.employee_id, project_id=payload.project_id, category_id=payload.category_id,
        description=payload.description, lines=[l.model_dump() for l in payload.lines], created_by=user.id,
    )
    db.commit()
    db.refresh(claim)
    return claim


@router.get("", response_model=list[ClaimOut])
def list_claims(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    employee_id: int | None = None, status_: str | None = None,
    mine: bool = False, pending_for_me: bool = False,
):
    q = db.query(EmployeeClaim)
    role = user.role.name

    if role == RoleName.EMPLOYEE:
        # Employees always see only their own claims, regardless of any other param.
        q = q.filter(EmployeeClaim.employee_id == user.employee_id)

    elif role == RoleName.MANAGER:
        if not user.employee_id:
            return []
        if mine:
            q = q.filter(EmployeeClaim.employee_id == user.employee_id)
        elif pending_for_me:
            q = q.join(Employee, EmployeeClaim.employee_id == Employee.id).filter(
                Employee.manager_id == user.employee_id, EmployeeClaim.status == ClaimStatus.SUBMITTED)
        else:
            # Default for a Manager: their direct reports' claims (any status).
            # A Manager never sees the company-wide claims list.
            q = q.join(Employee, EmployeeClaim.employee_id == Employee.id).filter(Employee.manager_id == user.employee_id)

    elif role == RoleName.ACCOUNTS:
        assigned_project_ids = project_scope_service.get_accounts_assigned_project_ids(db, user)
        if pending_for_me:
            q = (
                q.outerjoin(Project, EmployeeClaim.project_id == Project.id)
                .filter(EmployeeClaim.status == ClaimStatus.PENDING_ACCOUNTS_APPROVAL)
                .filter(or_(
                    Project.accounts_approver_id == user.id,
                    EmployeeClaim.project_id.is_(None),
                    and_(Project.accounts_approver_id.is_(None), EmployeeClaim.project_id.in_(assigned_project_ids)) if assigned_project_ids
                    else Project.id.is_(None),  # no assigned projects -> the fallback-pool clause never matches
                ))
            )
        else:
            # Project-scoped visibility: claims with no project (fallback
            # pool, unchanged) plus claims belonging to this Accounts user's
            # assigned projects. Zero assigned projects -> only no-project claims.
            q = q.filter(or_(EmployeeClaim.project_id.is_(None), EmployeeClaim.project_id.in_(assigned_project_ids)))
            if employee_id:
                q = q.filter(EmployeeClaim.employee_id == employee_id)

    else:  # ADMIN, SUPER_ADMIN, VIEWER
        if pending_for_me:
            q = q.filter(EmployeeClaim.status.in_([ClaimStatus.SUBMITTED, ClaimStatus.PENDING_ACCOUNTS_APPROVAL]))
        elif employee_id:
            q = q.filter(EmployeeClaim.employee_id == employee_id)

    if status_:
        q = q.filter(EmployeeClaim.status == status_)
    return q.order_by(EmployeeClaim.id.desc()).limit(500).all()


@router.get("/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_view(db, c, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this claim")
    return c


@router.get("/{claim_id}/download-pdf")
async def download_claim_pdf(claim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A single PDF: claim summary page, then one page per attachment
    (overall claim proof + every line's proof) - a complete copy of the
    claim an employee (or reviewer) can keep or file for reimbursement."""
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_view(db, c, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this claim")
    pdf_bytes = await claim_pdf_service.build_claim_pdf(db, c)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{c.claim_number}.pdf"'},
    )


@router.put("/{claim_id}", response_model=ClaimOut)
def update_claim(claim_id: int, payload: ClaimUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_edit(c, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only edit your own claims")
    _assert_claim_project_allowed(db, user, c.employee_id, payload.project_id)
    claim_service.update_draft_claim(
        db, c, project_id=payload.project_id, category_id=payload.category_id, description=payload.description,
        lines=[l.model_dump() for l in payload.lines], actor_id=user.id,
    )
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim(claim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_edit(c, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only delete your own claims")
    claim_service.delete_claim(db, c, user.id)
    db.commit()


@router.post("/{claim_id}/submit", response_model=ClaimOut)
def submit_claim(claim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_edit(c, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only submit your own claims")
    claim_service.submit_claim(db, c, user.id)
    db.commit()
    db.refresh(c)
    return c


@router.post("/{claim_id}/approve", response_model=ClaimOut, dependencies=[Depends(require_approver)])
def approve_claim(claim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    claim_service.approve_claim(db, c, user)
    db.commit()
    db.refresh(c)
    return c


@router.post("/{claim_id}/reject", response_model=ClaimOut, dependencies=[Depends(require_approver)])
def reject_claim(claim_id: int, payload: RejectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    claim_service.reject_claim(db, c, user, payload.reason)
    db.commit()
    db.refresh(c)
    return c
