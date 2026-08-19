"""
Storage abstraction layer supporting local filesystem and Google Drive.
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
    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default") -> dict:
        """Save file and return metadata."""
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
    
    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default") -> dict:
        """Save file to local filesystem organized by project/year/month/week."""
        now = dt.datetime.utcnow()
        iso_year, iso_week, _ = now.isocalendar()
        subdir = f"{project_code}/{now.year}/{now.month:02d}/W{iso_week:02d}"
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


class GoogleDriveStorageBackend(StorageBackend):
    """Store files in Google Drive."""
    
    def __init__(self):
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        except ImportError:
            raise ImportError(
                "google-auth and google-api-python-client are required for Google Drive backend. "
                "Install with: pip install google-auth-oauthlib google-api-python-client"
            )
        
        self.folder_id = settings.GDRIVE_FOLDER_ID
        if not self.folder_id:
            raise ValueError("EXPMS_GDRIVE_FOLDER_ID must be set for Google Drive storage")
        
        # Load credentials from JSON key file
        if not os.path.exists(settings.GDRIVE_CREDENTIALS_PATH):
            raise FileNotFoundError(f"Google Drive credentials file not found: {settings.GDRIVE_CREDENTIALS_PATH}")
        
        credentials = Credentials.from_service_account_file(
            settings.GDRIVE_CREDENTIALS_PATH,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        self.drive_service = build('drive', 'v3', credentials=credentials)
        
        # Store imports for later use
        self.MediaIoBaseDownload = MediaIoBaseDownload
    
    async def save_file(self, file_content: bytes, stored_filename: str, project_code: str = "default") -> dict:
        """Save file to Google Drive organized by project/year/month/week."""
        try:
            from googleapiclient.http import MediaInMemoryUpload
        except ImportError:
            raise ImportError("google-api-python-client is required")
        
        # Create folder structure (project_code/YYYY/MM/WXXX)
        now = dt.datetime.utcnow()
        iso_year, iso_week, _ = now.isocalendar()
        subdir = f"{project_code}/{now.year}/{now.month:02d}/W{iso_week:02d}"
        parent_folder_id = self._ensure_folder_path(subdir)
        
        # Upload file
        file_metadata = {
            'name': os.path.basename(stored_filename),
            'parents': [parent_folder_id],
            'mimeType': 'application/octet-stream',
        }
        
        media = MediaInMemoryUpload(file_content, mimetype='application/octet-stream')
        
        file_obj = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink'
        ).execute()
        
        file_id = file_obj.get('id')
        
        # Make file readable by the app's service account
        self.drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
            fields='id'
        ).execute()
        
        return {
            "file_path": file_id,
            "storage_url": file_id,
            "download_url": file_obj.get('webContentLink'),
            "view_url": file_obj.get('webViewLink'),
        }
    
    def _ensure_folder_path(self, path: str) -> str:
        """Create folder structure in Google Drive and return leaf folder ID."""
        parts = path.split('/')
        current_parent_id = self.folder_id
        
        for part in parts:
            # Check if folder exists
            query = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{current_parent_id}' in parents"
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            if files:
                current_parent_id = files[0]['id']
            else:
                # Create folder
                folder_metadata = {
                    'name': part,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [current_parent_id]
                }
                folder = self.drive_service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                current_parent_id = folder['id']
        
        return current_parent_id
    
    def get_file_url(self, stored_filename: str) -> str:
        """Get Google Drive file ID (stored_filename is the file ID)."""
        return f"https://drive.google.com/file/d/{stored_filename}/view"
    
    async def retrieve_file(self, stored_filename: str) -> bytes:
        """Retrieve file from Google Drive."""
        try:
            from io import BytesIO
        except ImportError:
            raise ImportError("io module is required")
        
        file_id = stored_filename
        
        try:
            # Download file
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = self.MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status_obj, done = downloader.next_chunk()
            
            return fh.getvalue()
        except Exception as e:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"File not found or inaccessible in Google Drive: {str(e)}"
            )
    
    def delete_file(self, stored_filename: str) -> bool:
        """Delete file from Google Drive."""
        try:
            file_id = stored_filename
            self.drive_service.files().delete(fileId=file_id).execute()
            return True
        except Exception:
            return False


# Factory function to get the appropriate storage backend
def get_storage_backend() -> StorageBackend:
    """Get the configured storage backend."""
    if settings.STORAGE_TYPE == "gdrive":
        return GoogleDriveStorageBackend()
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
