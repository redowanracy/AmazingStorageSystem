from typing import Dict, Type
# Import compatibility layer first
from .pkg_compatibility import *
from ..config import BucketConfig
from .base import StorageProvider
from .google_drive import GoogleDriveStorage
from .dropbox_storage import DropboxStorage
# Import other providers here when added
# from .onedrive import OneDriveStorage 

# Mapping from configuration type string to provider class
PROVIDER_MAP: Dict[str, Type[StorageProvider]] = {
    "google": GoogleDriveStorage,
    "dropbox": DropboxStorage,
    # "onedrive": OneDriveStorage, 
}

def get_storage_provider(bucket_config: BucketConfig) -> StorageProvider:
    """
    Factory function to create a storage provider instance based on config.

    Args:
        bucket_config: The configuration object for a specific bucket.

    Returns:
        An initialized instance of the appropriate StorageProvider subclass.

    Raises:
        ValueError: If the bucket type specified in the config is unknown.
    """
    provider_class = PROVIDER_MAP.get(bucket_config.type.lower())
    if provider_class:
        # Convert BucketConfig dataclass to a dict for the provider's __init__
        config_dict = {
            "credentials": bucket_config.credentials,
            "folder_id": bucket_config.folder_id,
            "folder_path": bucket_config.folder_path,
            # Add any other relevant fields from BucketConfig if needed
        }
        # Filter out None values as providers might not expect them
        filtered_config = {k: v for k, v in config_dict.items() if v is not None}
        
        try:
            # Pass additional args needed for specific providers (like Dropbox OAuth)
            if provider_class is DropboxStorage:
                from ..config import app_config # Import here to avoid circular dependency at top level
                if not app_config.dropbox_app_key or not app_config.dropbox_app_secret:
                     raise ValueError("Dropbox App Key/Secret not configured in environment (ASS_DROPBOX_APP_KEY, ASS_DROPBOX_APP_SECRET)")
                # Find the index of this bucket in the original config list
                provider_index = -1
                for idx, bc in enumerate(app_config.buckets):
                    # Compare based on a unique identifier if available (e.g., folder_path or credentials if they were still there)
                    # Here, we might assume order is preserved or use folder_path as a pseudo-ID
                    if bc.type == bucket_config.type and bc.folder_path == bucket_config.folder_path: 
                         provider_index = idx
                         break
                if provider_index == -1:
                     raise ValueError(f"Could not determine original index for Dropbox provider config: {bucket_config}")
                
                return DropboxStorage(
                    config=filtered_config, 
                    provider_index=provider_index,
                    app_key=app_config.dropbox_app_key,
                    app_secret=app_config.dropbox_app_secret
                )
            else:
                 # Other providers like GoogleDriveStorage still use the simple config
                 return provider_class(filtered_config)
        except Exception as e:
             print(f"Error initializing storage provider for type '{bucket_config.type}' with credentials '{bucket_config.credentials}': {e}")
             # Re-raise or handle more gracefully (e.g., return None, log error)
             raise # Re-raising helps identify initialization issues early
    else:
        raise ValueError(f"Unsupported storage provider type: '{bucket_config.type}'")

# You could also create a StorageManager class here that holds instances
# of all configured providers if that simplifies access elsewhere. 