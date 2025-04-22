import io
import os.path
from typing import List, Dict, Any, Tuple, Optional
import tempfile

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload, MediaFileUpload
from google.oauth2 import service_account
from google.auth.exceptions import GoogleAuthError

from .base import StorageProvider, StorageProviderError
from ..config import BucketConfig # Use BucketConfig for type hinting if desired

# If modifying these scopes, delete the previously saved credentials
# file (if using OAuth flow, not service account)
SCOPES = ["https://www.googleapis.com/auth/drive"]

class GoogleDriveStorage(StorageProvider):
    """Storage provider implementation for Google Drive."""

    def __init__(self, config: Dict[str, Any]):
        """Initializes the Google Drive client."""
        super().__init__(config)
        self.provider_type = "google"
        self.credentials_file = config.get("credentials")
        self.folder_id = config.get("folder_id") # Target folder ID
        if not self.credentials_file:
            raise ValueError("Google Drive 'credentials' path is required in config.")
        if not self.folder_id:
            raise ValueError("Google Drive 'folder_id' is required in config.")
        
        # Authenticate and get drive service
        try:
            self.drive_service = self._authenticate()
            self._ensure_folder_exists(self.folder_id)
            print(f"Successfully authenticated Google Drive for: {self.credentials_file}")
            print(f"Confirmed Google Drive folder exists: {self.folder_id}")
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Failed to initialize Google Drive storage: {str(e)}",
                original_error=e
            )

    def _authenticate(self) -> Resource:
        """Authenticates using service account credentials."""
        try:
            # Load credentials from the service account file
            scopes = ['https://www.googleapis.com/auth/drive']
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=scopes)
            
            # Build the drive service
            drive_service = build("drive", "v3", credentials=credentials)
            return drive_service
        except (GoogleAuthError, FileNotFoundError, ValueError) as e:
            raise StorageProviderError(
                self.provider_type,
                f"Authentication failed: {str(e)}",
                original_error=e
            )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unknown error during authentication: {str(e)}",
                original_error=e
            )

    def _ensure_folder_exists(self, folder_id: str):
         """Checks if the configured folder ID exists."""
         try:
             self.drive_service.files().get(fileId=folder_id).execute()
         except HttpError as e:
             if e.resp.status == 404:
                  raise StorageProviderError(
                      self.provider_type,
                      f"Folder with ID {folder_id} not found",
                      original_error=e
                  )
             else:
                  raise StorageProviderError(
                      self.provider_type,
                      f"Error checking folder existence: {str(e)}",
                      original_error=e
                  )

    def upload_chunk(self, chunk_data: bytes, chunk_name: str) -> str:
        """Uploads a chunk to the configured Google Drive folder."""
        temp_path = None
        try:
            # Create a temporary file and ensure it's properly closed before upload
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(chunk_data)
                # Ensure file is flushed and closed properly
                temp_file.flush()
            
            # File is now closed, upload the file to Google Drive
            file_metadata = {
                'name': chunk_name,
                'parents': [self.folder_id]
            }
            
            # Use with statement to ensure proper resource cleanup
            with open(temp_path, 'rb') as f:
                media = MediaFileUpload(temp_path, mimetype='application/octet-stream', resumable=True)
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
            
            # Return the file ID
            return file.get('id')
        except HttpError as e:
            raise StorageProviderError(
                self.provider_type,
                f"Failed to upload chunk {chunk_name}: {str(e)}",
                original_error=e
            )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unexpected error uploading chunk {chunk_name}: {str(e)}",
                original_error=e
            )
        finally:
            # Clean up the temporary file in a finally block to ensure it happens
            # even if an exception occurs
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    # Just log the error but don't raise, as we're already in exception handling
                    print(f"Warning: Failed to delete temporary file {temp_path}: {e}")

    def download_chunk(self, chunk_id: str) -> bytes:
        """Downloads a chunk using its Google Drive file ID."""
        try:
            # Get the file from Google Drive
            request = self.drive_service.files().get_media(fileId=chunk_id)
            
            # Download to a BytesIO object
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # Return the file content
            return file_content.getvalue()
        except HttpError as e:
            if e.resp.status == 404:
                raise FileNotFoundError(f"Chunk with ID {chunk_id} not found")
            else:
                raise StorageProviderError(
                    self.provider_type,
                    f"Failed to download chunk {chunk_id}: {str(e)}",
                    original_error=e
                )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unexpected error downloading chunk {chunk_id}: {str(e)}",
                original_error=e
            )

    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """Lists files/folders within the configured parent folder."""
        try:
            # In Google Drive, we use the folder ID directly
            folder_id = self.folder_id
            if folder_path:
                # If a subfolder path is provided, find its ID first
                # (implementation would depend on how you organize subfolders)
                pass
            
            # Query for files in the folder
            results = self.drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, size)"
            ).execute()
            
            files = results.get('files', [])
            
            # Format the response
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file.get('id'),
                    'name': file.get('name'),
                    'type': 'folder' if file.get('mimeType') == 'application/vnd.google-apps.folder' else 'file',
                    'size': int(file.get('size', 0))
                })
            
            return formatted_files
        except HttpError as e:
            raise StorageProviderError(
                self.provider_type,
                f"Failed to list files: {str(e)}",
                original_error=e
            )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unexpected error listing files: {str(e)}",
                original_error=e
            )

    def delete_chunk(self, chunk_id: str) -> bool:
        """Deletes a file (chunk) by its Google Drive ID."""
        try:
            self.drive_service.files().delete(fileId=chunk_id).execute()
            return True
        except HttpError as e:
            if e.resp.status == 404:
                # File already doesn't exist, consider deletion successful
                return True
            else:
                raise StorageProviderError(
                    self.provider_type,
                    f"Failed to delete chunk {chunk_id}: {str(e)}",
                    original_error=e
                )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unexpected error deleting chunk {chunk_id}: {str(e)}",
                original_error=e
            )

    def get_sizedata(self) -> Tuple[int, int]:
        """Gets storage quota information for the Drive account."""
        try:
            # Google Drive API doesn't provide a direct way to get storage quota
            # We'll calculate used space by summing up file sizes in our folder
            
            results = self.drive_service.files().list(
                q=f"'{self.folder_id}' in parents and trashed=false",
                fields="files(size)"
            ).execute()
            
            files = results.get('files', [])
            used_space = sum(int(file.get('size', 0)) for file in files)
            
            # For simplicity, we'll set a large arbitrary number for total space
            # In a real app, you'd use the Drive About API to get quota info
            total_space = 15 * 1024 * 1024 * 1024  # 15 GB (Google's free tier)
            
            return (total_space, used_space)
        except HttpError as e:
            raise StorageProviderError(
                self.provider_type,
                f"Failed to get size data: {str(e)}",
                original_error=e
            )
        except Exception as e:
            raise StorageProviderError(
                self.provider_type,
                f"Unexpected error getting size data: {str(e)}",
                original_error=e
            ) 