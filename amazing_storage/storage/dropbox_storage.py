import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode, FileMetadata, FolderMetadata, DeletedMetadata
from typing import List, Dict, Any, Tuple
import os # Add os import

from .base import StorageProvider
from ..config import BucketConfig 

class DropboxStorage(StorageProvider):
    """Storage provider implementation for Dropbox."""

    def __init__(self, config: Dict[str, Any]):
        """Initializes the Dropbox client."""
        super().__init__(config)
        self.credentials_file = config.get("credentials")
        self.folder_path = config.get("folder_path", "").rstrip('/') 
        if not self.credentials_file:
            raise ValueError("Dropbox 'credentials' path is required in config.")
        if not self.folder_path:
            print("Warning: Dropbox 'folder_path' not specified in config. Using root.")
        elif not self.folder_path.startswith('/'):
            self.folder_path = '/' + self.folder_path

        self.access_token = self._load_token()
        self.dbx = self._authenticate()
        self._ensure_folder_exists(self.folder_path)

    def _load_token(self) -> str:
        """Loads the access token from the credentials file."""
        try:
            with open(self.credentials_file, 'r') as f:
                token = f.read().strip()
            if not token:
                raise ValueError(f"Credentials file '{self.credentials_file}' is empty.")
            return token
        except FileNotFoundError:
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")
        except Exception as e:
            raise IOError(f"Error reading credentials file '{self.credentials_file}': {e}")

    def _authenticate(self) -> dropbox.Dropbox:
        """Authenticates using the access token."""
        try:
            cert_path = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
            if not cert_path:
                print("Warning: SSL certificate path not found in environment variables (SSL_CERT_FILE or REQUESTS_CA_BUNDLE). Using default verification.")

            session = dropbox.create_session()
            if cert_path:
                session.verify = cert_path
            
            dbx = dropbox.Dropbox(self.access_token, session=session)
            dbx.users_get_current_account() 
            print("Successfully authenticated with Dropbox.")
            return dbx
        except AuthError:
            print(f"Authentication failed: Invalid Dropbox access token in '{self.credentials_file}'.")
            raise
        except Exception as e:
            print(f"An error occurred during Dropbox authentication: {e}")
            raise

    def _ensure_folder_exists(self, folder_path: str):
        """Creates the base folder if it doesn't exist."""
        if not folder_path or folder_path == "/":
            return 
        try:
            try:
                self.dbx.files_get_metadata(folder_path)
                print(f"Confirmed Dropbox folder exists: {folder_path}")
            except ApiError as e:
                if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path() and e.error.get_path().is_not_found():
                    print(f"Dropbox folder '{folder_path}' not found, creating...")
                    self.dbx.files_create_folder_v2(folder_path)
                    print(f"Created Dropbox folder: {folder_path}")
                else:
                    raise 
        except ApiError as error:
            print(f"Error ensuring Dropbox folder '{folder_path}' exists: {error}")
            raise

    def _get_full_path(self, name: str) -> str:
        """Constructs the full path for an item within the base folder."""
        if self.folder_path and name.startswith('/'):
            name = name[1:] 
        return f"{self.folder_path}/{name}"

    def upload_chunk(self, chunk_data: bytes, chunk_name: str) -> str:
        """Uploads a chunk to the configured Dropbox folder."""
        full_path = self._get_full_path(chunk_name)
        try:

            metadata = self.dbx.files_upload(
                chunk_data,
                full_path,
                mode=WriteMode('overwrite') 
            )
            print(f"Uploaded chunk '{chunk_name}' to Dropbox path: {metadata.path_display}")
            return metadata.path_display 
        except ApiError as error:
            print(f"An error occurred uploading chunk '{chunk_name}' to Dropbox path '{full_path}': {error}")
            raise

    def download_chunk(self, chunk_id: str) -> bytes:
        """Downloads a chunk using its Dropbox path."""
        try:
            metadata, res = self.dbx.files_download(path=chunk_id)
            print(f"Downloaded chunk from Dropbox path: {metadata.path_display}")
            return res.content
        except ApiError as error:
            if isinstance(error.error, dropbox.files.DownloadError) and error.error.is_path() and error.error.get_path().is_not_found():
                raise FileNotFoundError(f"Chunk with path '{chunk_id}' not found in Dropbox.")
            else:
                print(f"An error occurred downloading chunk '{chunk_id}' from Dropbox: {error}")
                raise

    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """Lists files/folders within a specified path relative to the base folder."""
        list_path = self.folder_path if not folder_path else self._get_full_path(folder_path)
        if list_path == "/": list_path = "" 

        results = []
        try:
            res = self.dbx.files_list_folder(path=list_path, recursive=False) 
            while True:
                for entry in res.entries:
                    item_type = 'unknown'
                    size = 0
                    if isinstance(entry, FileMetadata):
                        item_type = 'file'
                        size = entry.size
                    elif isinstance(entry, FolderMetadata):
                        item_type = 'folder'
                    elif isinstance(entry, DeletedMetadata):
                        continue 
                    
                    results.append({
                        'id': entry.path_display, 
                        'name': entry.name,
                        'type': item_type,
                        'size': size
                    })
                
                if not res.has_more:
                    break
                res = self.dbx.files_list_folder_continue(res.cursor)

            return results
        except ApiError as error:
            if isinstance(error.error, dropbox.files.ListFolderError) and error.error.is_path() and error.error.get_path().is_not_found():
                print(f"Folder '{list_path}' not found in Dropbox.")
                return [] 
            else:
                print(f"An error occurred listing files in Dropbox path '{list_path}': {error}")
                raise

    def delete_chunk(self, chunk_id: str) -> bool:
        """Deletes a file (chunk) by its Dropbox path."""
        try:
            metadata = self.dbx.files_delete_v2(path=chunk_id)
            print(f"Deleted chunk '{metadata.metadata.name}' from Dropbox path: {chunk_id}")
            return True
        except ApiError as error:
            if isinstance(error.error, dropbox.files.DeleteError) and error.error.is_path_lookup() and error.error.get_path_lookup().is_not_found():
                print(f"Chunk path '{chunk_id}' not found for deletion in Dropbox.")
                return False
            else:
                print(f"An error occurred deleting chunk '{chunk_id}' from Dropbox: {error}")
                return False

    def get_sizedata(self) -> Tuple[int, int]:
        """Gets storage usage information for the Dropbox account."""
        try:
            space_usage = self.dbx.users_get_space_usage()
            total_size = space_usage.allocation.get_individual().allocated if space_usage.allocation.is_individual() else space_usage.allocation.get_team().allocated if space_usage.allocation.is_team() else 0 # Total allocated space in bytes
            used_size = space_usage.used 
            return total_size, used_size
        except ApiError as error:
            print(f"An error occurred fetching space usage from Dropbox: {error}")
            return (0, 0) 
        except Exception as e: 
            print(f"An unexpected error occurred fetching space usage: {e}")
            return (0, 0) 