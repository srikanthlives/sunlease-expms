from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.models import AuditLog, ApprovalRule

router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.get("/audit-logs")
def list_audit_logs(
    db: Session = Depends(get_db), _=Depends(get_current_user),
    entity_type: str | None = None, entity_id: int | None = None, limit: int = 200,
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    logs = q.order_by(AuditLog.id.desc()).limit(min(limit, 1000)).all()
    return [
        {"id": l.id, "entity_type": l.entity_type, "entity_id": l.entity_id, "action": l.action,
         "actor_id": l.actor_id, "details": l.details, "created_at": l.created_at}
        for l in logs
    ]


class ApprovalRuleIn(BaseModel):
    name: str
    entity_type: str = "CLAIM"
    min_amount: float = 0
    max_amount: float | None = None
    required_steps: str  # comma-separated role names
    is_active: bool = True


@router.get("/approval-rules")
def list_approval_rules(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(ApprovalRule).order_by(ApprovalRule.min_amount).all()


@router.post("/approval-rules", dependencies=[Depends(require_admin)])
def create_approval_rule(payload: ApprovalRuleIn, db: Session = Depends(get_db)):
    rule = ApprovalRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule
