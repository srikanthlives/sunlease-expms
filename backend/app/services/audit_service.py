import json

from sqlalchemy.orm import Session

from app.models.models import AuditLog


def record(db: Session, entity_type: str, entity_id: int, action: str, actor_id: int | None, details: dict | None = None):
    """Append an immutable audit log entry. Does not commit - caller controls
    the transaction boundary so this can be part of a larger atomic operation."""
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(log)
    return log
