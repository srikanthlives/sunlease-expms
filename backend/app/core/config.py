import os
from typing import ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Expense & Payment Management System"
    SECRET_KEY: str = os.environ.get("EXPMS_SECRET_KEY", "dev-secret-change-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    DATABASE_URL: str = os.environ.get("EXPMS_DATABASE_URL", "sqlite:///../data/expms.db")
    
    # Storage backend: 'local' or 'gdrive' (Google Drive)
    STORAGE_TYPE: str = os.environ.get("EXPMS_STORAGE_TYPE", "local")
    
    # Local storage settings
    UPLOAD_DIR: str = os.environ.get("EXPMS_UPLOAD_DIR", "../data/uploads")
    
    # Google Drive storage settings
    GDRIVE_FOLDER_ID: str = os.environ.get("EXPMS_GDRIVE_FOLDER_ID", "")
    GDRIVE_CREDENTIALS_PATH: str = os.environ.get("EXPMS_GDRIVE_CREDENTIALS_PATH", "./gdrive-credentials.json")
    
    # File upload restrictions
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("EXPMS_MAX_UPLOAD_SIZE_MB", "15"))
    
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
