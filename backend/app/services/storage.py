"""
Storage abstraction layer supporting local filesystem and Cloudflare R2.
"""
import datetime as dt
import os
from abc import ABC, abstractmethod
from io import BytesIO

from fastapi import HTTPException, status

from app.core.config import settings


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default", category: str = "misc", subdir_override: str | None = None) -> dict:
        """Save file and return metadata. `subdir_override`, when given,
        replaces the usual <category>/<project>/<year>/<month>/W<week> path
        entirely (e.g. grouping employee claim attachments by claim id
        instead of upload date)."""
        pass
    
    @abstractmethod
    def get_file_url(self, stored_filename: str) -> str:
        """Get file URL or path for retrieval."""
        pass
    
    @abstractmethod
    async def retrieve_file(self, stored_filename: str) -> bytes:
        """Retrieve file content."""
        pass
    
    @abstractmethod
    def delete_file(self, stored_filename: str) -> bool:
        """Delete a file. Returns True if successful."""
        pass


class LocalStorageBackend(StorageBackend):
    """Store files on local filesystem."""
    
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default", category: str = "misc", subdir_override: str | None = None) -> dict:
        """Save file to local filesystem organized by document category/project/year/month/week
        (or by `subdir_override` verbatim, when given)."""
        if subdir_override is not None:
            subdir = subdir_override
        else:
            now = dt.datetime.utcnow()
            iso_year, iso_week, _ = now.isocalendar()
            subdir = f"{category}/{project_code}/{now.year}/{now.month:02d}/W{iso_week:02d}"
        dir_path = os.path.join(self.upload_dir, subdir)
        os.makedirs(dir_path, exist_ok=True)
        
        dest_path = os.path.join(dir_path, os.path.basename(stored_filename))
        
        with open(dest_path, "wb") as f:
            f.write(file_content)
        
        return {
            "file_path": dest_path,
            "storage_url": f"{subdir}/{os.path.basename(stored_filename)}",
        }
    
    def get_file_url(self, stored_filename: str) -> str:
        """Get file path for local storage."""
        return os.path.join(self.upload_dir, stored_filename)
    
    async def retrieve_file(self, stored_filename: str) -> bytes:
        """Retrieve file from local filesystem."""
        file_path = self.get_file_url(stored_filename)
        if not os.path.exists(file_path):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        
        with open(file_path, "rb") as f:
            return f.read()
    
    def delete_file(self, stored_filename: str) -> bool:
        """Delete file from local filesystem."""
        file_path = self.get_file_url(stored_filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception:
            return False


class R2StorageBackend(StorageBackend):
    """Store files in a Cloudflare R2 bucket (S3-compatible API), under a
    fixed root prefix (default 'SUNLEASE') so every upload lands in one
    identifiable place in the bucket."""

    def __init__(self):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            raise ImportError(
                "boto3 is required for R2 storage. Install with: pip install boto3"
            )

        if not settings.R2_ACCOUNT_ID and not settings.R2_ENDPOINT_URL:
            raise ValueError("EXPMS_R2_ACCOUNT_ID (or EXPMS_R2_ENDPOINT_URL) must be set for R2 storage")
        if not settings.R2_ACCESS_KEY_ID or not settings.R2_SECRET_ACCESS_KEY:
            raise ValueError("EXPMS_R2_ACCESS_KEY_ID and EXPMS_R2_SECRET_ACCESS_KEY must be set for R2 storage")
        if not settings.R2_BUCKET_NAME:
            raise ValueError("EXPMS_R2_BUCKET_NAME must be set for R2 storage")

        endpoint_url = settings.R2_ENDPOINT_URL or f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        print(f"[INFO] Using Cloudflare R2 storage: bucket='{settings.R2_BUCKET_NAME}', prefix='{settings.R2_PREFIX}'")

        self.bucket = settings.R2_BUCKET_NAME
        self.prefix = settings.R2_PREFIX.strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    def _key(self, relative_key: str) -> str:
        return f"{self.prefix}/{relative_key}" if self.prefix else relative_key

    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default", category: str = "misc", subdir_override: str | None = None) -> dict:
        """Save file to R2 organized by SUNLEASE/category/project/YYYY/MM/WXXX
        (or by `subdir_override` verbatim, when given)."""
        if subdir_override is not None:
            subdir = subdir_override
        else:
            now = dt.datetime.utcnow()
            iso_year, iso_week, _ = now.isocalendar()
            subdir = f"{category}/{project_code}/{now.year}/{now.month:02d}/W{iso_week:02d}"
        relative_key = f"{subdir}/{os.path.basename(stored_filename)}"
        key = self._key(relative_key)

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=file_content,
            ContentType="application/octet-stream",
        )

        return {
            "file_path": key,
            "storage_url": relative_key,
        }

    def get_file_url(self, stored_filename: str) -> str:
        """Return the full R2 object key for the given relative key."""
        return self._key(stored_filename)

    async def retrieve_file(self, stored_filename: str) -> bytes:
        """Retrieve file from R2."""
        key = self._key(stored_filename)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"File not found or inaccessible in R2: {str(e)}"
            )

    def delete_file(self, stored_filename: str) -> bool:
        """Delete file from R2."""
        key = self._key(stored_filename)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


# Factory function to get the appropriate storage backend
def get_storage_backend() -> StorageBackend:
    """Get the configured storage backend."""
    if settings.STORAGE_TYPE == "r2":
        return R2StorageBackend()
    else:
        return LocalStorageBackend()


# Global storage instance
_storage_backend = None


def get_storage() -> StorageBackend:
    """Get the storage backend instance (singleton)."""
    global _storage_backend
    if _storage_backend is None:
        _storage_backend = get_storage_backend()
    return _storage_backend
