from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.deps import get_current_user, require_accounts
from app.db.session import get_db
from app.models.models import User
from app.services import bulk_import_service

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
