import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_roles
from app.db.session import get_db
from app.models.enums import RoleName, EditRequestStatus
from app.models.models import EditRequest, User
from app.schemas.edit_requests import EditRequestCreate, EditRequestOut, EditRequestApprove, EditRequestReject
from app.services import edit_request_service

router = APIRouter(prefix="/api/v1/edit-requests", tags=["edit-requests"])

# Only Accounts proposes edits through this queue - Admin/Super Admin edit
# the entities directly via PUT /expenses|invoices|payments/{id} instead.
require_requester = require_roles(RoleName.ACCOUNTS)


def _to_out(req: EditRequest) -> EditRequestOut:
    return EditRequestOut(
        id=req.id, entity_type=req.entity_type, entity_id=req.entity_id,
        changes=json.loads(req.changes), previous_values=json.loads(req.previous_values),
        status=req.status, requested_by=req.requested_by,
        requested_by_name=(req.requester.full_name or req.requester.username) if req.requester else None,
        requested_at=req.requested_at, reviewed_by=req.reviewed_by,
        reviewed_by_name=(req.reviewer.full_name or req.reviewer.username) if req.reviewer else None,
        reviewed_at=req.reviewed_at, review_remarks=req.review_remarks,
    )


@router.post("", response_model=EditRequestOut, dependencies=[Depends(require_requester)])
def create_edit_request(payload: EditRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = edit_request_service.create_edit_request(db, payload.entity_type, payload.entity_id, payload.changes, user)
    db.commit()
    db.refresh(req)
    return _to_out(req)


@router.get("", response_model=list[EditRequestOut])
def list_edit_requests(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    status_: str | None = None, entity_type: str | None = None, mine: bool = False,
):
    q = db.query(EditRequest)
    # Accounts only ever sees their own requests (pending + their history).
    # Admin/Super Admin see everything - that's the review queue + full history.
    if user.role.name == RoleName.ACCOUNTS or mine:
        q = q.filter(EditRequest.requested_by == user.id)
    elif user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to edit requests")
    if status_:
        q = q.filter(EditRequest.status == status_)
    if entity_type:
        q = q.filter(EditRequest.entity_type == entity_type)
    reqs = q.order_by(EditRequest.id.desc()).limit(500).all()
    return [_to_out(r) for r in reqs]


@router.get("/{request_id}", response_model=EditRequestOut)
def get_edit_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = db.query(EditRequest).filter(EditRequest.id == request_id).first()
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edit request not found")
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN) and req.requested_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this edit request")
    return _to_out(req)


@router.post("/{request_id}/approve", response_model=EditRequestOut, dependencies=[Depends(require_admin)])
def approve_edit_request(request_id: int, payload: EditRequestApprove, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = db.query(EditRequest).filter(EditRequest.id == request_id).first()
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edit request not found")
    edit_request_service.approve_edit_request(db, req, user, payload.remarks)
    db.commit()
    db.refresh(req)
    return _to_out(req)


@router.post("/{request_id}/reject", response_model=EditRequestOut, dependencies=[Depends(require_admin)])
def reject_edit_request(request_id: int, payload: EditRequestReject, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = db.query(EditRequest).filter(EditRequest.id == request_id).first()
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edit request not found")
    edit_request_service.reject_edit_request(db, req, user, payload.reason)
    db.commit()
    db.refresh(req)
    return _to_out(req)
