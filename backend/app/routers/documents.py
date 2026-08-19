import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Document, User, Project, Expense, Invoice, EmployeeClaim, EmployeeClaimLine
from app.models.enums import DocumentType
from app.schemas.transactions import DocumentOut
from app.services.document_service import save_upload
from app.services.storage import get_storage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


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

    # Get project code for folder organization
    project_code = "default"
    project_id = None
    
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

    meta = await save_upload(db, file, uploaded_by=user.id, project_code=project_code)
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
        # Google Drive: stream file from cloud storage
        file_content = await storage.retrieve_file(doc.stored_filename)
        return StreamingResponse(
            iter([file_content]),
            media_type=doc.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"'}
        )
