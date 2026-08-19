import datetime as dt
import os
import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.enums import AuditAction
from app.services import audit_service
from app.services.storage import get_storage


def _safe_extension(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File type '{ext}' is not allowed")
    return ext


def _unique_dest_path(ext: str) -> str:
    """Returns a unique filename (UUID4 with extension) for storage."""
    return f"{uuid.uuid4().hex}{ext}"


async def save_upload(db, file: UploadFile, *, uploaded_by: int, project_code: str = "default") -> dict:
    """Validates MIME/extension/size, saves to configured storage backend, and
    returns metadata for a Document row. Does not create the Document row
    itself - caller links it to the right entity. Organizes files by project
    folder, year, month, and week."""
    ext = _safe_extension(file.filename)
    if file.content_type not in settings.ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"MIME type '{file.content_type}' is not allowed")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File exceeds max upload size of {settings.MAX_UPLOAD_SIZE_MB}MB")
    if len(contents) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    # Generate unique filename
    stored_filename = _unique_dest_path(ext)
    
    # Save using configured storage backend with project folder organization
    storage = get_storage()
    storage_result = await storage.save_file(contents, stored_filename, project_code=project_code)
    
    return {
        "original_filename": file.filename,
        "stored_filename": storage_result.get("storage_url", stored_filename),
        "file_path": storage_result.get("file_path"),
        "mime_type": file.content_type,
        "file_size": len(contents),
    }
