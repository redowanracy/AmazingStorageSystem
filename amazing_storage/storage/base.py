from abc import ABC, abstractmethod
from typing import List, Dict, Any, IO, Tuple

class StorageProviderError(Exception):
    """Exception raised for errors in the storage providers.
    
    Attributes:
        provider_type -- the type of provider that raised the error
        message -- explanation of the error
        original_error -- the original exception that was raised (if any)
    """
    
    def __init__(self, provider_type: str, message: str, original_error=None):
        self.provider_type = provider_type
        self.message = message
        self.original_error = original_error
        super().__init__(f"{provider_type} provider error: {message}")

class StorageProvider(ABC):
    """Abstract base class for all storage providers."""

    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        """Initializes the storage provider with its specific configuration."""
        self.config = config
        self.provider_type = "unknown"  # To be set by implementing classes

    @abstractmethod
    def upload_chunk(self, chunk_data: bytes, chunk_name: str) -> str:
        """
        Uploads a chunk of data to the storage.

        Args:
            chunk_data: The byte content of the chunk.
            chunk_name: A unique name for the chunk (e.g., filename_part_001).

        Returns:
            A unique identifier or path for the uploaded chunk within this provider.
            
        Raises:
            StorageProviderError: If there is an error uploading the chunk.
        """
        pass

    @abstractmethod
    def download_chunk(self, chunk_id: str) -> bytes:
        """
        Downloads a chunk of data from the storage.

        Args:
            chunk_id: The unique identifier returned by upload_chunk.

        Returns:
            The byte content of the chunk.
        
        Raises:
            StorageProviderError: If there is an error downloading the chunk.
            FileNotFoundError: If the chunk_id does not exist.
        """
        pass

    @abstractmethod
    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """
        Lists files and folders within a specified path. 
        For simplicity in this distributed system, this might primarily list 
        metadata files stored at the root or chunk manifests.
        
        Args:
            folder_path: The path within the provider's storage to list (optional).

        Returns:
            A list of dictionaries, each representing a file or folder 
            with keys like 'name', 'id', 'type' ('file' or 'folder'), 'size'.
            
        Raises:
            StorageProviderError: If there is an error listing files.
        """
        pass

    @abstractmethod
    def delete_chunk(self, chunk_id: str) -> bool:
        """
        Deletes a specific chunk from the storage.

        Args:
            chunk_id: The unique identifier of the chunk to delete.

        Returns:
            True if deletion was successful, False otherwise.
            
        Raises:
            StorageProviderError: If there is an error deleting the chunk.
        """
        pass

    @abstractmethod
    def get_sizedata(self) -> Tuple[int, int]:
        """
        Returns the total size and used size of the storage bucket.

        Returns:
            A tuple containing (total_size_bytes, used_size_bytes).
            
        Raises:
            StorageProviderError: If there is an error getting size data.
        """
        pass 