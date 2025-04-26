import json
import time
from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox.oauth import OAuth2FlowResult
import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode, FileMetadata, FolderMetadata, DeletedMetadata
from typing import List, Dict, Any, Tuple, Optional
import os
from .base import StorageProvider

TOKEN_DIR = "." # Store tokens in project root for simplicity; use a more secure location in production.

class DropboxStorage(StorageProvider):
    """Storage provider implementation for Dropbox using OAuth 2 with refresh tokens."""

    def __init__(self, config: Dict[str, Any], provider_index: int, app_key: str, app_secret: str):
        """Initializes the Dropbox client configuration."""
        super().__init__(config)
        self.folder_path = config.get("folder_path", "").rstrip('/')
        self.provider_index = provider_index
        self.app_key = app_key
        self.app_secret = app_secret
        self.token_file_path = os.path.join(TOKEN_DIR, f"dropbox_tokens_{self.provider_index}.json")

        if not self.app_key or not self.app_secret:
            raise ValueError("Dropbox App Key and Secret are required for OAuth flow.")

        if not self.folder_path:
            print(f"Warning: Dropbox provider {self.provider_index} 'folder_path' not specified. Using root.")
        elif not self.folder_path.startswith('/'):
            self.folder_path = '/' + self.folder_path

        # Check for stored refresh token
        stored_token_data = self._load_token_data()
        if stored_token_data and 'refresh_token' in stored_token_data:
            print(f"Dropbox provider {self.provider_index}: Found stored refresh token.")
        else:
            print(f"Dropbox provider {self.provider_index}: No stored refresh token found.")
            print(f"  Visit http://127.0.0.1:5000/dropbox_auth/{self.provider_index} to authorize.")

    def _get_token_file_path(self) -> str:
        """Gets the path to the token storage file for this provider instance."""
        return os.path.join(TOKEN_DIR, f"dropbox_tokens_{self.provider_index}.json")

    def _load_token_data(self) -> Optional[Dict[str, Any]]:
        """Loads token data (access, refresh, expires) from the JSON file."""
        path = self._get_token_file_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading token file {path}: {e}")
            return None

    def _save_token_data(self, token_result: OAuth2FlowResult = None, refresh_token: str = None, access_token: str = None, expires_at: float = None):
        """Saves token data to the JSON file."""
        path = self._get_token_file_path()
        data_to_save = {}

        if token_result:
            data_to_save = {
                "access_token": token_result.access_token,
                "refresh_token": getattr(token_result, 'refresh_token', None),
                "expires_at": time.time() + getattr(token_result, 'expires_in', 3600) if hasattr(token_result, 'expires_in') else None,
                "account_id": getattr(token_result, 'account_id', None),
                "scope": getattr(token_result, 'scope', None),
                "token_type": getattr(token_result, 'token_type', 'bearer')
            }
            print(f"Received token data for provider {self.provider_index}:")
            for key, value in data_to_save.items():
                print(f"  {key}: {value if key != 'access_token' else '***'}")
        elif refresh_token or access_token:
             existing_data = self._load_token_data() or {}
             if refresh_token:
                 existing_data["refresh_token"] = refresh_token
             if access_token:
                 existing_data["access_token"] = access_token
             if expires_at:
                 existing_data["expires_at"] = expires_at
             data_to_save = existing_data
        else:
            print(f"Warning: No token data provided to save for provider {self.provider_index}.")
            return

        try:
            with open(path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            print(f"Saved token data for Dropbox provider {self.provider_index} to {path}")
        except IOError as e:
            print(f"Error saving token file {path}: {e}")

    def _get_refreshed_client(self) -> dropbox.Dropbox:
        """Gets an authenticated Dropbox client, refreshing the access token if necessary."""
        token_data = self._load_token_data()
        access_token = token_data.get("access_token") if token_data else None
        refresh_token = token_data.get("refresh_token") if token_data else None
        expires_at = token_data.get("expires_at") if token_data else None

        if not refresh_token:
             raise AuthError(f"Provider {self.provider_index} not authorized. No refresh token found. Visit /dropbox_auth/{self.provider_index}", None)

        # Check if access token is missing or expired (allow buffer time)
        if not access_token or (expires_at and expires_at < time.time() - 60):
            print(f"Dropbox provider {self.provider_index}: Access token expired or missing. Refreshing...")
            try:
                # Use the refresh token to get a new access token via the SDK
                dbx_temp = dropbox.Dropbox(
                    app_key=self.app_key,
                    app_secret=self.app_secret,
                    oauth2_refresh_token=refresh_token
                )
                dbx_temp.check_and_refresh_access_token()

                new_access_token = dbx_temp.oauth2_access_token
                new_expires_at = dbx_temp.oauth2_access_token_expiration

                # Save new access token, keep original refresh token
                self._save_token_data(
                    refresh_token=refresh_token,
                    access_token=new_access_token,
                    expires_at=new_expires_at.timestamp() if new_expires_at else None
                )
                print(f"Dropbox provider {self.provider_index}: Token refreshed successfully.")
                return dropbox.Dropbox(new_access_token)

            except ApiError as e:
                print(f"Dropbox provider {self.provider_index}: Failed to refresh access token: {e}")
                raise AuthError(f"Failed to refresh token for provider {self.provider_index}. Visit /dropbox_auth/{self.provider_index}", e)
            except Exception as e:
                 print(f"Unexpected error refreshing token for provider {self.provider_index}: {e}")
                 raise AuthError(f"Unexpected error refreshing token for provider {self.provider_index}", e)
        else:
            # Token is likely valid, use existing access token
            return dropbox.Dropbox(access_token)

    def _ensure_folder_exists(self, folder_path: str):
        """Creates the base folder if it doesn't exist."""
        if not folder_path or folder_path == "/":
            return
        try:
            dbx = self._get_refreshed_client()
            try:
                dbx.files_get_metadata(folder_path)
            except ApiError as e:
                if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path() and e.error.get_path().is_not_found():
                    print(f"Dropbox folder '{folder_path}' not found for provider {self.provider_index}, creating...")
                    dbx.files_create_folder_v2(folder_path)
                    print(f"Created Dropbox folder: {folder_path} for provider {self.provider_index}")
                else:
                    raise
        except ApiError as error:
            print(f"Error ensuring Dropbox folder '{folder_path}' exists for provider {self.provider_index}: {error}")
        except AuthError as auth_error:
             print(f"AuthError ensuring folder exists for provider {self.provider_index}: {auth_error}. Needs authorization.")

    def _get_full_path(self, name: str) -> str:
        """Constructs the full path for an item within the base folder."""
        if self.folder_path and name.startswith('/'):
            name = name[1:]
        return f"{self.folder_path}/{name}"

    def upload_chunk(self, chunk_data: bytes, chunk_name: str) -> str:
        """Uploads a chunk using a refreshed client."""
        full_path = self._get_full_path(chunk_name)
        try:
            dbx = self._get_refreshed_client()
            self._ensure_folder_exists(self.folder_path)
            metadata = dbx.files_upload(
                chunk_data,
                full_path,
                mode=WriteMode('overwrite')
            )
            return metadata.path_display
        except ApiError as error:
            print(f"An error occurred uploading chunk '{chunk_name}' to Dropbox path '{full_path}' for provider {self.provider_index}: {error}")
            raise
        except AuthError as auth_error:
             print(f"AuthError uploading chunk for provider {self.provider_index}: {auth_error}. Needs authorization.")
             raise

    def download_chunk(self, chunk_id: str) -> bytes:
        """Downloads a chunk using a refreshed client."""
        try:
            dbx = self._get_refreshed_client()
            metadata, res = dbx.files_download(path=chunk_id)
            return res.content
        except ApiError as error:
            if isinstance(error.error, dropbox.files.DownloadError) and error.error.is_path() and error.error.get_path().is_not_found():
                raise FileNotFoundError(f"Chunk with path '{chunk_id}' not found in Dropbox for provider {self.provider_index}.")
            else:
                print(f"An error occurred downloading chunk '{chunk_id}' from Dropbox for provider {self.provider_index}: {error}")
                raise
        except AuthError as auth_error:
             print(f"AuthError downloading chunk for provider {self.provider_index}: {auth_error}. Needs authorization.")
             raise

    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """Lists files using a refreshed client."""
        list_path = self.folder_path if not folder_path else self._get_full_path(folder_path)
        if list_path == "/": list_path = ""

        results = []
        try:
            dbx = self._get_refreshed_client()
            # Removed ensure_folder_exists here as list_folder handles not_found
            res = dbx.files_list_folder(path=list_path, recursive=False)
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
                res = dbx.files_list_folder_continue(res.cursor)

            return results
        except ApiError as error:
            if isinstance(error.error, dropbox.files.ListFolderError) and error.error.is_path() and error.error.get_path().is_not_found():
                print(f"Folder '{list_path}' not found in Dropbox for provider {self.provider_index}.")
                return []
            else:
                print(f"An error occurred listing files in Dropbox path '{list_path}' for provider {self.provider_index}: {error}")
                return [] # Return empty list on error
        except AuthError as auth_error:
             print(f"AuthError listing files for provider {self.provider_index}: {auth_error}. Needs authorization.")
             return [] # Return empty list on auth error

    def delete_chunk(self, chunk_id: str) -> bool:
        """Deletes a file using a refreshed client."""
        try:
            dbx = self._get_refreshed_client()
            metadata = dbx.files_delete_v2(path=chunk_id)
            return True
        except ApiError as error:
            if isinstance(error.error, dropbox.files.DeleteError) and error.error.is_path_lookup() and error.error.get_path_lookup().is_not_found():
                print(f"Chunk path '{chunk_id}' not found for deletion in Dropbox for provider {self.provider_index}.")
                return False # Treat as success if not found
            else:
                print(f"An error occurred deleting chunk '{chunk_id}' from Dropbox for provider {self.provider_index}: {error}")
                return False
        except AuthError as auth_error:
             print(f"AuthError deleting chunk for provider {self.provider_index}: {auth_error}. Needs authorization.")
             return False # Treat auth error as failure to delete

    def get_sizedata(self) -> Tuple[int, int]:
        """Gets storage usage using a refreshed client."""
        try:
            dbx = self._get_refreshed_client() # Get authenticated client
            space_usage = dbx.users_get_space_usage()
            total_size = space_usage.allocation.get_individual().allocated if space_usage.allocation.is_individual() else space_usage.allocation.get_team().allocated if space_usage.allocation.is_team() else 0
            used_size = space_usage.used
            return total_size, used_size
        except ApiError as error:
            print(f"An error occurred fetching space usage from Dropbox for provider {self.provider_index}: {error}")
            return (0, 0)
        except AuthError as auth_error:
             print(f"AuthError getting size data for provider {self.provider_index}: {auth_error}. Needs authorization.")
             return (0, 0)
        except Exception as e:
            print(f"An unexpected error occurred fetching space usage for provider {self.provider_index}: {e}")
            return (0, 0) 