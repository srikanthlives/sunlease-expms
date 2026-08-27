import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Document, User, Project, Expense, Invoice, EmployeeClaim, EmployeeClaimLine
from app.models.enums import DocumentType, ClaimStatus, RoleName
from app.schemas.transactions import DocumentOut
from app.services.document_service import save_upload
from app.services.storage import get_storage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _category_folder(document_type: str) -> str:
    """Top-level storage folder for a document type - configurable via
    EXPMS_DOCUMENT_FOLDER_* env vars (see core/config.py) so the layout can
    be renamed/reorganized without a code change."""
    return {
        DocumentType.EXPENSE: settings.DOCUMENT_FOLDER_EXPENSE,
        DocumentType.INVOICE: settings.DOCUMENT_FOLDER_INVOICE,
        DocumentType.PAYMENT: settings.DOCUMENT_FOLDER_PAYMENT,
        DocumentType.CLAIM: settings.DOCUMENT_FOLDER_CLAIM,
        DocumentType.CLAIM_LINE: settings.DOCUMENT_FOLDER_CLAIM,
    }.get(document_type, "misc")


def _claim_for_document_link(db: Session, claim_id: int | None, claim_line_id: int | None) -> EmployeeClaim | None:
    if claim_id:
        return db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
    if claim_line_id:
        line = db.query(EmployeeClaimLine).filter(EmployeeClaimLine.id == claim_line_id).first()
        return db.query(EmployeeClaim).filter(EmployeeClaim.id == line.claim_id).first() if line else None
    return None


def _authorize_claim_document_change(db: Session, user: User, claim_id: int | None, claim_line_id: int | None):
    """Attachments on a claim/claim-line follow the same edit window as the
    claim itself: only the owning employee (or Admin/Super Admin) may add or
    remove them, and only while the claim is still DRAFT or REJECTED - once
    it's submitted, it's out of the employee's hands."""
    claim = _claim_for_document_link(db, claim_id, claim_line_id)
    if claim is None:
        return
    if user.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        return
    if user.employee_id != claim.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only manage attachments on your own claims")
    if claim.status not in (ClaimStatus.DRAFT, ClaimStatus.REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Attachments can only be changed while the claim is a draft or rejected")


@router.post("", response_model=DocumentOut)
async def upload_document(
    document_type: str = Form(...),
    expense_id: int | None = Form(None),
    claim_id: int | None = Form(None),
    claim_line_id: int | None = Form(None),
    invoice_id: int | None = Form(None),
    payment_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if document_type not in (DocumentType.EXPENSE, DocumentType.INVOICE, DocumentType.CLAIM, DocumentType.CLAIM_LINE, DocumentType.PAYMENT):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid document_type")
    if not any([expense_id, claim_id, claim_line_id, invoice_id, payment_id]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Document must be linked to at least one entity")
    _authorize_claim_document_change(db, user, claim_id, claim_line_id)

    # Get project code for folder organization
    project_code = "default"
    project_id = None
    claim = None

    # Determine project_id from the linked entity
    if expense_id:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if expense:
            project_id = expense.project_id
    elif invoice_id:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if invoice:
            project_id = invoice.project_id
    elif claim_id:
        claim = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_id).first()
        if claim:
            project_id = claim.project_id
    elif claim_line_id:
        claim_line = db.query(EmployeeClaimLine).filter(EmployeeClaimLine.id == claim_line_id).first()
        if claim_line and claim_line.claim_id:
            claim = db.query(EmployeeClaim).filter(EmployeeClaim.id == claim_line.claim_id).first()
            if claim:
                project_id = claim.project_id
    
    # Get project code if project exists
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project_code = project.code

    category = _category_folder(document_type)
    # Employee claim attachments are grouped by claim, not upload date - a
    # claim's overall attachment and every line's proof end up in the same
    # folder, keyed by claim number, so everything for one claim is in one
    # place regardless of when each file was added or resubmitted.
    subdir_override = f"{project_code}/{category}/{claim.claim_number}" if claim else None
    meta = await save_upload(db, file, uploaded_by=user.id, project_code=project_code, category=category, subdir_override=subdir_override)
    doc = Document(
        expense_id=expense_id, claim_id=claim_id, claim_line_id=claim_line_id, invoice_id=invoice_id,
        payment_id=payment_id, document_type=document_type, uploaded_by=user.id, **meta,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/by-entity", response_model=list[DocumentOut])
def list_by_entity(
    db: Session = Depends(get_db), _=Depends(get_current_user),
    expense_id: int | None = None, claim_id: int | None = None, claim_line_id: int | None = None,
    invoice_id: int | None = None, payment_id: int | None = None,
):
    q = db.query(Document)
    if expense_id:
        q = q.filter(Document.expense_id == expense_id)
    if claim_id:
        q = q.filter(Document.claim_id == claim_id)
    if claim_line_id:
        q = q.filter(Document.claim_line_id == claim_line_id)
    if invoice_id:
        q = q.filter(Document.invoice_id == invoice_id)
    if payment_id:
        q = q.filter(Document.payment_id == payment_id)
    return q.order_by(Document.id.desc()).all()


@router.get("/for-claim/{claim_id}", response_model=list[DocumentOut])
def list_claim_documents(claim_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Every document tied to a claim, whether attached to the claim
    overall or to one of its lines - used for the read-only combined view
    on the Expenses page (a claim's consolidated expense links back to the
    whole claim, not any one line)."""
    line_ids = [row[0] for row in db.query(EmployeeClaimLine.id).filter(EmployeeClaimLine.claim_id == claim_id).all()]
    q = db.query(Document).filter(or_(Document.claim_id == claim_id, Document.claim_line_id.in_(line_ids) if line_ids else False))
    return q.order_by(Document.id.desc()).all()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if doc.claim_id or doc.claim_line_id:
        _authorize_claim_document_change(db, user, doc.claim_id, doc.claim_line_id)
    elif user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admin/Super Admin can delete this attachment")
    get_storage().delete_file(doc.stored_filename)
    db.delete(doc)
    db.commit()


@router.get("/{document_id}/download")
async def download_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Authorization for every download, per file-security requirement. All
    # authenticated users may currently download (role-scoping can be tightened
    # per document type later); the key control is that this endpoint - not a
    # static file path - is the only way to fetch a document.
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    
    storage = get_storage()
    
    if settings.STORAGE_TYPE == "local":
        # Local storage: return file directly
        if not os.path.exists(doc.file_path):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on server")
        return FileResponse(doc.file_path, media_type=doc.mime_type, filename=doc.original_filename)
    else:
        # Remote storage (R2 etc.): stream file from cloud storage
        file_content = await storage.retrieve_file(doc.stored_filename)
        return StreamingResponse(
            iter([file_content]),
            media_type=doc.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"'}
        )
