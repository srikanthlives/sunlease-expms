import datetime as dt
import os
import shutil

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin, require_super_admin
from app.db.session import SessionLocal, engine, get_db
from app.models.models import AuditLog, ApprovalRule, User
from app.models.enums import AuditAction
from app.services import audit_service

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


# Database backup / restore - Super Admin only. Built for environments like
# Railway where there's no dashboard file browser for the mounted volume, so
# this is the only way to pull a copy of expms.db or push a replacement one.
SQLITE_MAGIC = b"SQLite format 3\x00"


def _sqlite_path() -> str:
    if not settings.DATABASE_URL.startswith("sqlite"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Database backup/restore is only supported for SQLite deployments")
    return settings.DATABASE_URL.split("sqlite:///", 1)[1]


@router.get("/admin/db-backup", dependencies=[Depends(require_super_admin)])
def download_db_backup(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    path = _sqlite_path()
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Database file not found")
    # Flush any WAL-mode pending writes into the main file first, so the
    # downloaded copy is a complete, consistent snapshot rather than
    # missing whatever hasn't been checkpointed yet.
    with engine.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
    audit_service.record(db, "SYSTEM", 0, AuditAction.UPDATE, actor.id, {"action": "db_backup_downloaded"})
    db.commit()
    filename = f"expms-backup-{dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.post("/admin/db-restore", dependencies=[Depends(require_super_admin)])
async def restore_db(
    file: UploadFile = File(...), confirm: str = Form(...), actor: User = Depends(get_current_user),
):
    if confirm != "REPLACE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type REPLACE to confirm this destructive action")
    path = _sqlite_path()
    contents = await file.read()
    if len(contents) < len(SQLITE_MAGIC) or contents[: len(SQLITE_MAGIC)] != SQLITE_MAGIC:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is not a valid SQLite database")

    # Validate on a throwaway copy before touching the live file - never
    # overwrite a working database with something that turns out corrupt.
    tmp_path = f"{path}.upload.tmp"
    with open(tmp_path, "wb") as f:
        f.write(contents)
    tmp_engine = create_engine(f"sqlite:///{tmp_path}")
    try:
        with tmp_engine.connect() as conn:
            result = conn.execute(text("PRAGMA integrity_check")).scalar()
        if result != "ok":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Uploaded database failed integrity check: {result}")
    finally:
        tmp_engine.dispose()

    # Keep the current database as a dated backup alongside the live file -
    # this restore is reversible even though it wasn't asked to be undoable.
    if os.path.exists(path):
        backup_path = f"{path}.before-restore-{dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, backup_path)

    engine.dispose()  # release pooled connections/file handles on the current file before replacing it
    shutil.move(tmp_path, path)

    # The uploaded db may be from an older schema version - bring it up to
    # date the same additive way a normal startup would.
    from app.migrate import migrate
    migrate(verbose=False)

    # A fresh session, opened only after the swap above, so this audit
    # entry (and everything after it) lands in the newly-restored database
    # rather than a stale connection still pointing at the old file.
    new_db = SessionLocal()
    try:
        audit_service.record(new_db, "SYSTEM", 0, AuditAction.UPDATE, actor.id, {"action": "db_restored", "filename": file.filename})
        new_db.commit()
    finally:
        new_db.close()

    return {"detail": "Database restored. A backup of the previous database was saved alongside it on the server."}
