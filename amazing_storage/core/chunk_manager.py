import os
import math
import hashlib
import time
import datetime
from typing import List, Optional, Iterator, Tuple

from ..config import app_config
from ..storage import StorageProvider, get_storage_provider
from .metadata import MetadataManager, FileManifest, ChunkInfo

# Simple round-robin strategy for provider selection
class RoundRobinStrategy:
    def __init__(self, num_providers: int):
        if num_providers <= 0:
            raise ValueError("Number of providers must be positive.")
        self.num_providers = num_providers
        self.current_index = 0

    def get_next_provider_index(self) -> int:
        index = self.current_index
        self.current_index = (self.current_index + 1) % self.num_providers
        return index


class ChunkManager:
    """Handles splitting files, distributing chunks, and reassembling files."""

    def __init__(self, metadata_manager: MetadataManager):
        """Initialize the chunk manager with storage providers from config."""
        self.metadata_manager = metadata_manager
        self.chunk_size = app_config.chunk_size
        self.providers = []
        
        # Initialize all providers from config
        print("Initializing storage providers for ChunkManager...")
        for idx, bucket_config in enumerate(app_config.buckets):
            try:
                provider = get_storage_provider(bucket_config)
                self.providers.append(provider)
                print(f"  Provider {idx} ({bucket_config.type}) added to ChunkManager.")
            except Exception as e:
                print(f"  Failed to initialize provider {idx} ({bucket_config.type}): {e}")
        
        if not self.providers:
            print("WARNING: No storage providers were initialized successfully.")
        else:
            print(f"ChunkManager active with {len(self.providers)} providers.")
            print(f"ChunkManager initialized with chunk size: {self.chunk_size / (1024 * 1024):.2f} MB")
        
        # Initialize distribution strategy
        self.distribution_strategy = RoundRobinStrategy(len(self.providers)) if self.providers else None

    def _read_file_in_chunks(self, file_path: str) -> Iterator[bytes]:
        """Reads a file and yields chunks of data."""
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except FileNotFoundError:
             print(f"Error: Input file not found at {file_path}")
             raise
        except IOError as e:
             print(f"Error reading file {file_path}: {e}")
             raise

    def upload_file(self, file_path: str, original_filename: str = None, file_id: str = None, version_notes: str = "") -> str:
        """
        Split a file into chunks and distribute across providers.
        
        Args:
            file_path: Path to the file to upload
            original_filename: The original filename (if different from file_path basename)
            file_id: If provided, updates an existing file by creating a new version
            version_notes: Notes for this version if updating an existing file
            
        Returns:
            The file_id of the uploaded file
        """
        if not self.providers:
            raise ValueError("No storage providers are available")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist")
            
        if not original_filename:
            original_filename = os.path.basename(file_path)
            
        existing_manifest = None
        if file_id:
            existing_manifest = self.metadata_manager.load_manifest(file_id)
            if not existing_manifest:
                print(f"Warning: Specified file_id {file_id} not found. Creating new file instead.")
                file_id = None
        
        # Generate a unique file ID if not updating an existing file
        if not file_id:
            file_id = self.metadata_manager.generate_file_id()
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create a new manifest or use existing one
        if existing_manifest:
            manifest = existing_manifest
        else:
            manifest = FileManifest(
                file_id=file_id,
                original_filename=original_filename,
                total_size=file_size,
                chunk_size=self.chunk_size,
            )
        
        print(f"Starting upload for '{original_filename}' (Size: {file_size / (1024 * 1024):.2f} MB, File ID: {file_id})")
        
        uploaded_chunks = []
        
        try:
            # Read file and split into chunks
            chunks = []
            # Use binary mode and close the file properly
            with open(file_path, 'rb') as f:
                chunk_idx = 0
                
                while True:
                    chunk_data = f.read(self.chunk_size)
                    if not chunk_data:
                        break  # End of file
                        
                    chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                    
                    provider_idx = chunk_idx % len(self.providers)
                    provider = self.providers[provider_idx]
                    chunk_name = f"{file_id}_chunk_{chunk_idx}_{int(time.time())}"
                    
                    print(f"  Uploading chunk {chunk_idx} ({len(chunk_data)} bytes, hash: {chunk_hash[:8]}...) to provider {provider_idx} ({provider.__class__.__name__}) as '{chunk_name}'")
                    try:
                        chunk_id = provider.upload_chunk(chunk_data, chunk_name)
                        uploaded_chunks.append((provider_idx, chunk_id))
                        
                        chunk_info = ChunkInfo(
                            chunk_index=chunk_idx,
                            size=len(chunk_data),
                            hash=chunk_hash,
                            provider_index=provider_idx,
                            chunk_id=chunk_id
                        )
                        chunks.append(chunk_info)
                        
                        chunk_idx += 1
                    except Exception as e:
                        print(f"Error uploading chunk {chunk_idx}: {e}")
                        # Ensure cleanup before raising
                        self._cleanup_failed_upload(uploaded_chunks)
                        raise
            
            # Add a new version with these chunks
            if existing_manifest:
                version_notes = version_notes or f"Updated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                manifest.add_version(chunks, notes=version_notes)
                print(f"Added new version for '{original_filename}' with {len(chunks)} chunks.")
            else:
                # For new files, the first version is created implicitly
                manifest.add_version(chunks, notes="Initial version")
            
            # Save the manifest after all chunks are uploaded
            self.metadata_manager.save_manifest(manifest)
            print(f"Successfully {'updated' if existing_manifest else 'uploaded'} '{original_filename}' with {len(chunks)} chunks. Manifest saved.")
            
            return file_id
            
        except Exception as e:
            print(f"Error during upload of '{original_filename}': {e}")
            # Clean up any chunks that were uploaded before the error
            self._cleanup_failed_upload(uploaded_chunks)
            raise # Re-raise the exception

    def _cleanup_failed_upload(self, uploaded_chunks: List[Tuple[int, str]]):
        """Attempts to delete chunks uploaded before a failure occurred."""
        if not uploaded_chunks:
            return
        print("Attempting to clean up chunks from failed upload...")
        for provider_index, chunk_id in uploaded_chunks:
            try:
                provider = self.providers[provider_index]
                print(f"  Deleting chunk '{chunk_id}' from provider {provider_index} ({provider.__class__.__name__})...")
                provider.delete_chunk(chunk_id)
            except Exception as delete_error:
                # Log error but continue cleanup
                print(f"  Warning: Failed to delete chunk '{chunk_id}' during cleanup: {delete_error}")
        print("Cleanup attempt finished.")

    def download_file(self, file_id: str, output_path: str) -> bool:
        """
        Download and reconstruct a file from its chunks.
        
        Args:
            file_id: The ID of the file to download
            output_path: Where to save the reconstructed file
            
        Returns:
            True if successful, raises exception otherwise
        """
        # Load the manifest
        manifest = self.metadata_manager.load_manifest(file_id)
        if not manifest:
            raise FileNotFoundError(f"No manifest found for file {file_id}")
            
        # Create output directory if needed
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Open output file
        with open(output_path, 'wb') as f:
            # Download each chunk in order
            for chunk_info in sorted(manifest.chunks, key=lambda x: x.chunk_index):
                # Get the appropriate provider
                if chunk_info.provider_index >= len(self.providers):
                    raise ValueError(f"Provider index {chunk_info.provider_index} out of range")
                    
                provider = self.providers[chunk_info.provider_index]
                
                # Download the chunk
                chunk_data = provider.download_chunk(chunk_info.chunk_id)
                
                # Verify hash
                chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                if chunk_hash != chunk_info.hash:
                    raise ValueError(f"Chunk {chunk_info.chunk_index} hash mismatch: expected {chunk_info.hash}, got {chunk_hash}")
                
                # Write to file
                f.write(chunk_data)
        
        return True

    def delete_file(self, file_id: str) -> bool:
        """
        Deletes a file by removing all its chunks and its manifest.

        Args:
            file_id: The unique ID of the file to delete.

        Returns:
            True if deletion was successful (or file didn't exist), False otherwise.
        """
        manifest = self.metadata_manager.load_manifest(file_id)
        if not manifest:
            print(f"Manifest not found for file ID: {file_id}. Assuming already deleted.")
            return True # Nothing to delete

        print(f"Starting deletion for file '{manifest.original_filename}' (ID: {file_id})")
        
        all_chunks_deleted = True
        for chunk_info in manifest.chunks:
            provider_index = chunk_info.provider_index
            chunk_id = chunk_info.chunk_id
            try:
                if provider_index < len(self.providers):
                    provider = self.providers[provider_index]
                    print(f"  Deleting chunk {chunk_info.chunk_index} (ID: '{chunk_id}') from provider {provider_index} ({provider.__class__.__name__})...")
                    success = provider.delete_chunk(chunk_id)
                    if not success:
                         # Log error but continue trying to delete other chunks
                         print(f"  Warning: Failed to delete chunk {chunk_info.chunk_index} (ID: '{chunk_id}') from provider {provider_index}. It might already be deleted or an error occurred.")
                         # Depends on desired strictness if this should mark all_chunks_deleted as False.
                else:
                    print(f"  Warning: Provider index {provider_index} for chunk {chunk_info.chunk_index} is out of bounds. Cannot delete.")
                    all_chunks_deleted = False # Indicate an issue
            except Exception as e:
                 print(f"  Error deleting chunk {chunk_info.chunk_index} (ID: '{chunk_id}') from provider {provider_index}: {e}")
                 all_chunks_deleted = False # Indicate an issue

        # After attempting to delete all chunks, delete the manifest
        manifest_deleted = self.metadata_manager.delete_manifest(file_id)

        if not manifest_deleted:
             print(f"Warning: Failed to delete manifest file for ID: {file_id}")

        if all_chunks_deleted and manifest_deleted:
            print(f"Successfully deleted file '{manifest.original_filename}' (ID: {file_id}).")
            return True
        else:
            print(f"Deletion process for file '{manifest.original_filename}' (ID: {file_id}) completed with warnings or errors.")
            return False # Indicate potential issues

    def list_files(self) -> List[Tuple[str, str]]:
         """Lists files based on available manifests."""
         return self.metadata_manager.list_manifests() 