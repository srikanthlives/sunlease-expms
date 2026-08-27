import os
from typing import ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Expense & Payment Management System"
    SECRET_KEY: str = os.environ.get("EXPMS_SECRET_KEY", "dev-secret-change-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    DATABASE_URL: str = os.environ.get("EXPMS_DATABASE_URL", "sqlite:///../data/expms.db")
    
    # Storage backend: 'local' or 'r2' (Cloudflare R2)
    STORAGE_TYPE: str = os.environ.get("EXPMS_STORAGE_TYPE", "local")

    # Local storage settings
    UPLOAD_DIR: str = os.environ.get("EXPMS_UPLOAD_DIR", "../data/uploads")

    # Cloudflare R2 storage settings (used when EXPMS_STORAGE_TYPE=r2)
    R2_ACCOUNT_ID: str = os.environ.get("EXPMS_R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.environ.get("EXPMS_R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.environ.get("EXPMS_R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME: str = os.environ.get("EXPMS_R2_BUCKET_NAME", "")
    # Optional override - by default derived from the account id as
    # https://<account_id>.r2.cloudflarestorage.com
    R2_ENDPOINT_URL: str = os.environ.get("EXPMS_R2_ENDPOINT_URL", "")
    # Root "folder" (key prefix) under which every uploaded file is stored in the bucket.
    R2_PREFIX: str = os.environ.get("EXPMS_R2_PREFIX", "SUNLEASE")
    
    # File upload restrictions
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("EXPMS_MAX_UPLOAD_SIZE_MB", "15"))

    # Top-level folder each document type is stored under (see
    # services/storage.py) - <folder>/<project-code>/<YYYY>/<MM>/W<week>/<uuid4>.<ext>,
    # under either the local upload dir or the R2 prefix. Override any of
    # these to rename/relocate that category without touching code; existing
    # files already on disk/R2 are unaffected (only new uploads use it).
    DOCUMENT_FOLDER_EXPENSE: str = os.environ.get("EXPMS_DOCUMENT_FOLDER_EXPENSE", "expenses")
    DOCUMENT_FOLDER_INVOICE: str = os.environ.get("EXPMS_DOCUMENT_FOLDER_INVOICE", "invoices")
    DOCUMENT_FOLDER_PAYMENT: str = os.environ.get("EXPMS_DOCUMENT_FOLDER_PAYMENT", "payments")
    # Used for both CLAIM (overall claim attachment) and CLAIM_LINE (per-line proof).
    DOCUMENT_FOLDER_CLAIM: str = os.environ.get("EXPMS_DOCUMENT_FOLDER_CLAIM", "employee-claims")
    
    # Parse comma-separated extension list
    # NOTE: no type annotation on these three - they're computed here in plain
    # Python from the raw env var, not left for pydantic-settings to parse.
    # An annotated `set`/`list` field makes pydantic-settings try to JSON-decode
    # the matching EXPMS_* env var itself, which blows up on our comma-separated
    # (non-JSON) values.
    _allowed_extensions = os.environ.get("EXPMS_ALLOWED_UPLOAD_EXTENSIONS", ".pdf,.jpg,.jpeg,.png,.webp,.xlsx,.csv")
    ALLOWED_UPLOAD_EXTENSIONS: ClassVar[set] = {ext.strip() for ext in _allowed_extensions.split(",")}

    # Parse comma-separated MIME type list
    _allowed_mime_types = os.environ.get(
        "EXPMS_ALLOWED_UPLOAD_MIME_TYPES",
        "application/pdf,image/jpeg,image/png,image/webp,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
    )
    ALLOWED_UPLOAD_MIME_TYPES: ClassVar[set] = {mime.strip() for mime in _allowed_mime_types.split(",")}

    # CORS Origins
    _cors_origins = os.environ.get("EXPMS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    CORS_ORIGINS: ClassVar[list] = [origin.strip() for origin in _cors_origins.split(",")]

    class Config:
        env_prefix = "EXPMS_"


settings = Settings()

# Initialize local storage directory if using local storage
if settings.STORAGE_TYPE == "local":
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
