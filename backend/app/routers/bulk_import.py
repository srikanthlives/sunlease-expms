import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.deps import get_current_user, require_accounts, require_admin
from app.db.session import get_db
from app.models.models import User
from app.services import bulk_import_service, fund_import_service

router = APIRouter(prefix="/api/v1/bulk-import", tags=["bulk-import"])

_ALLOWED_EXT = (".xlsx", ".xlsm")


@router.get("/template", dependencies=[Depends(require_accounts)])
def download_template():
    content = bulk_import_service.build_template_workbook()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=expense_bulk_import_template.xlsx"},
    )


@router.get("/export", dependencies=[Depends(require_accounts)])
def export_expenses(
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
    project_id: int | None = Query(None),
    include_cancelled: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Existing expenses in the import template's layout - edit and
    re-upload, or just use it as a spreadsheet extract."""
    content = bulk_import_service.build_export_workbook(
        db, date_from=date_from, date_to=date_to, project_id=project_id,
        include_cancelled=include_cancelled)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=expense_export.xlsx"},
    )


@router.post("/expenses", dependencies=[Depends(require_accounts)])
async def bulk_import_expenses(
    dry_run: bool = True,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .xlsx/.xlsm files are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    try:
        result = bulk_import_service.process_workbook(db, content, user, dry_run=dry_run)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read workbook: {exc}")
    return result


# ---- Fund transfers / funding ----
# Admin/Super Admin only, matching the Funds module itself (routers/funds.py)
# rather than the require_accounts used for the expense import above.
@router.get("/funds-template", dependencies=[Depends(require_admin)])
def download_funds_template():
    content = fund_import_service.build_template_workbook()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fund_transfers_import_template.xlsx"},
    )


@router.post("/fund-transfers", dependencies=[Depends(require_admin)])
async def bulk_import_fund_transfers(
    dry_run: bool = True,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .xlsx/.xlsm files are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    try:
        result = fund_import_service.process_workbook(db, content, user, dry_run=dry_run)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read workbook: {exc}")
    return result


@router.get("/funds-export", dependencies=[Depends(require_admin)])
def export_fund_transfers(
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
    funding_entity_id: int | None = Query(None),
    kind: str | None = Query(None),
    include_cancelled: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Existing transfers in the import template's layout - edit and
    re-upload, or just use it as a spreadsheet extract."""
    content = fund_import_service.build_export_workbook(
        db, date_from=date_from, date_to=date_to, funding_entity_id=funding_entity_id,
        kind=kind, include_cancelled=include_cancelled)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fund_transfers_export.xlsx"},
    )
