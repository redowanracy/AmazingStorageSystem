import io
import os.path
from typing import List, Dict, Any, Tuple, Optional

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

from .base import StorageProvider
from ..config import BucketConfig # Use BucketConfig for type hinting if desired

# If modifying these scopes, delete the previously saved credentials
# file (if using OAuth flow, not service account)
SCOPES = ["https://www.googleapis.com/auth/drive"]

class GoogleDriveStorage(StorageProvider):
    """Storage provider implementation for Google Drive."""

    def __init__(self, config: Dict[str, Any]):
        """Initializes the Google Drive client."""
        super().__init__(config)
        self.credentials_file = config.get("credentials")
        self.folder_id = config.get("folder_id") # Target folder ID
        if not self.credentials_file:
            raise ValueError("Google Drive 'credentials' path is required in config.")
        if not self.folder_id:
            raise ValueError("Google Drive 'folder_id' is required in config.")
        
        self.service = self._authenticate()
        # Ensure the target folder exists (optional, prevents errors later)
        self._ensure_folder_exists(self.folder_id) 

    def _authenticate(self) -> Resource:
        """Authenticates using service account credentials."""
        creds = None
        if os.path.exists(self.credentials_file):
            creds = Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES)
        else:
             raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")

        # Service account credentials don't typically expire like user OAuth tokens.
        # The main validation happens when building the service.
        # if not creds or not creds.valid: <--- REMOVE THIS BLOCK
        #      raise Exception("Could not obtain valid Google Drive credentials.")

        try:
            service = build("drive", "v3", credentials=creds)
            # Add a simple check after building the service
            service.about().get(fields='user').execute() 
            print(f"Successfully authenticated Google Drive for: {self.credentials_file}")
            return service
        except HttpError as error:
            print(f"An error occurred authenticating/building the Drive service for {self.credentials_file}: {error}")
            # Potentially check error.resp.status for specific auth issues (e.g., 401, 403)
            raise ConnectionRefusedError(f"Failed to authenticate Google Drive for {self.credentials_file}: {error}")
        except Exception as e: # Catch other potential errors during build/check
             print(f"An unexpected error occurred during Google Drive authentication for {self.credentials_file}: {e}")
             raise ConnectionRefusedError(f"Unexpected error authenticating Google Drive for {self.credentials_file}: {e}")

    def _ensure_folder_exists(self, folder_id: str):
         """Checks if the configured folder ID exists."""
         try:
             self.service.files().get(fileId=folder_id, fields='id').execute()
             print(f"Confirmed Google Drive folder exists: {folder_id}")
         except HttpError as error:
             if error.resp.status == 404:
                  raise FileNotFoundError(f"Google Drive folder with ID '{folder_id}' not found or insufficient permissions.")
             else:
                  print(f"An error occurred checking folder existence: {error}")
                  raise

    def upload_chunk(self, chunk_data: bytes, chunk_name: str) -> str:
        """Uploads a chunk to the configured Google Drive folder."""
        file_metadata = {
            "name": chunk_name,
            "parents": [self.folder_id] # Specify the parent folder
        }
        media = MediaIoBaseUpload(io.BytesIO(chunk_data),
                                  mimetype='application/octet-stream', # Use generic mime type for chunks
                                  resumable=True) # Good for large chunks/unstable connections
        try:
            file = self.service.files().create(body=file_metadata,
                                               media_body=media,
                                               fields='id').execute()
            print(f"Uploaded chunk '{chunk_name}' to Google Drive. File ID: {file.get('id')}")
            return file.get("id")
        except HttpError as error:
            print(f"An error occurred uploading chunk '{chunk_name}' to Google Drive: {error}")
            # Consider specific error handling (e.g., retries for 5xx errors)
            raise # Re-raise the exception for the caller to handle

    def download_chunk(self, chunk_id: str) -> bytes:
        """Downloads a chunk using its Google Drive file ID."""
        request = self.service.files().get_media(fileId=chunk_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        try:
            while done is False:
                status, done = downloader.next_chunk()
                # print(f"Download {int(status.progress() * 100)}%.") # Optional progress
            print(f"Downloaded chunk ID '{chunk_id}' from Google Drive.")
            return fh.getvalue()
        except HttpError as error:
             if error.resp.status == 404:
                  raise FileNotFoundError(f"Chunk with ID '{chunk_id}' not found in Google Drive.")
             else:
                  print(f"An error occurred downloading chunk ID '{chunk_id}' from Google Drive: {error}")
                  raise

    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """Lists files/folders within the configured parent folder."""
        # Note: folder_path is ignored here as we list within the fixed self.folder_id
        # If needed, could search for subfolders by name within self.folder_id
        query = f"'{self.folder_id}' in parents and trashed = false"
        results = []
        page_token = None
        try:
            while True:
                response = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, size)',
                    pageToken=page_token
                ).execute()
                
                for file in response.get('files', []):
                    file_type = 'folder' if file.get('mimeType') == 'application/vnd.google-apps.folder' else 'file'
                    # Drive API might not return size for certain file types like Google Docs
                    size = int(file.get('size', 0)) 
                    results.append({
                        'id': file.get('id'),
                        'name': file.get('name'),
                        'type': file_type,
                        'size': size 
                    })
                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break
            return results
        except HttpError as error:
            print(f"An error occurred listing files in Google Drive folder '{self.folder_id}': {error}")
            raise

    def delete_chunk(self, chunk_id: str) -> bool:
        """Deletes a file (chunk) by its Google Drive ID."""
        try:
            self.service.files().delete(fileId=chunk_id).execute()
            print(f"Deleted chunk ID '{chunk_id}' from Google Drive.")
            return True
        except HttpError as error:
             if error.resp.status == 404:
                  print(f"Chunk ID '{chunk_id}' not found for deletion in Google Drive.")
                  return False # Or raise FileNotFoundError depending on desired behavior
             else:
                print(f"An error occurred deleting chunk ID '{chunk_id}' from Google Drive: {error}")
                return False # Indicate deletion failed

    def get_sizedata(self) -> Tuple[int, int]:
        """Gets storage quota information for the Drive account."""
        try:
            about = self.service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            total_size = int(quota.get('limit', 0)) # In bytes
            used_size = int(quota.get('usage', 0)) # In bytes
            # usageInDrive = int(quota.get('usageInDrive', 0))
            # usageInDriveTrash = int(quota.get('usageInDriveTrash', 0))
            return total_size, used_size
        except HttpError as error:
             print(f"An error occurred fetching storage quota from Google Drive: {error}")
             # Return (0, 0) or raise an error, depending on how critical this info is
             return (0, 0) 