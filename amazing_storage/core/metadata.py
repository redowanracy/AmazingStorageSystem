"""
Metadata management for the Amazing Storage System.

This module handles the creation, storage, and retrieval of file manifests,
which track how files are split into chunks and distributed across storage providers.
"""

import json
import os
import uuid
import time
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

METADATA_DIR = "metadata" # Local directory to store manifest files

@dataclass
class ChunkInfo:
    """Information about a single chunk of a file."""
    chunk_index: int        # 0-based index of the chunk
    chunk_id: str           # ID returned by the storage provider (e.g., file ID, path)
    provider_index: int     # Index of the provider in the config.buckets list
    size: int               # Size of this specific chunk in bytes
    hash: Optional[str] = None # Optional hash (e.g., SHA256) for integrity checks

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chunk_index": self.chunk_index,
            "chunk_id": self.chunk_id,
            "provider_index": self.provider_index,
            "size": self.size,
            "hash": self.hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkInfo':
        """Create from dictionary after deserialization."""
        return cls(
            chunk_index=data.get("chunk_index", data.get("index", 0)),
            chunk_id=data.get("chunk_id", ""),
            provider_index=data.get("provider_index", 0),
            size=data.get("size", 0),
            hash=data.get("hash", "")
        )

class FileVersion:
    """Information about a specific version of a file."""
    
    def __init__(self, version_id: str, timestamp: float, chunks: List[ChunkInfo], 
                 is_current: bool = True, notes: str = ""):
        self.version_id = version_id
        self.timestamp = timestamp
        self.chunks = chunks
        self.is_current = is_current
        self.notes = notes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "timestamp_readable": datetime.datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "is_current": self.is_current,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileVersion':
        """Create from dictionary after deserialization."""
        return cls(
            version_id=data.get("version_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            chunks=[ChunkInfo.from_dict(chunk) for chunk in data.get("chunks", [])],
            is_current=data.get("is_current", True),
            notes=data.get("notes", "")
        )

@dataclass
class FileManifest:
    """Manifest tracking all information about a file in the system."""
    # Fields without defaults must come first
    original_filename: str 
    total_size: int
    chunk_size: int # The chunk size used for *this* file
    # Fields with defaults follow
    file_id: str = field(default_factory=lambda: str(uuid.uuid4())) # Unique ID for this stored file
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    versions: List[FileVersion] = field(default_factory=list)
    # Optional: Add creation timestamp, last modified, encryption details, etc.

    @property
    def chunks(self) -> List[ChunkInfo]:
        """Get chunks from the current version for backward compatibility."""
        current_version = self.get_current_version()
        return current_version.chunks if current_version else []
    
    def add_version(self, chunks: List[ChunkInfo], notes: str = "") -> str:
        """
        Add a new version of the file.
        
        Returns the new version ID.
        """
        for version in self.versions:
            version.is_current = False
        
        version_id = str(uuid.uuid4())
        version = FileVersion(
            version_id=version_id,
            timestamp=time.time(),
            chunks=chunks,
            is_current=True,
            notes=notes
        )
        
        self.versions.append(version)
        self.updated_at = version.timestamp
        
        return version_id
    
    def get_current_version(self) -> Optional[FileVersion]:
        """Get the current version of the file."""
        for version in self.versions:
            if version.is_current:
                return version
        return None if not self.versions else self.versions[-1]
    
    def set_current_version(self, version_id: str) -> bool:
        """
        Set a specific version as the current version.
        Returns True if successful, False otherwise.
        """
        # Reset all versions
        for version in self.versions:
            if version.version_id == version_id:
                version.is_current = True
                self.updated_at = time.time()
                return True
            else:
                version.is_current = False
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        created_at_readable = datetime.datetime.fromtimestamp(self.created_at).strftime('%Y-%m-%d %H:%M:%S')
        updated_at_readable = datetime.datetime.fromtimestamp(self.updated_at).strftime('%Y-%m-%d %H:%M:%S')
        
        return {
            "file_id": self.file_id,
            "original_filename": self.original_filename,
            "total_size": self.total_size,
            "chunk_size": self.chunk_size,
            "created_at": self.created_at,
            "created_at_readable": created_at_readable,
            "updated_at": self.updated_at,
            "updated_at_readable": updated_at_readable,
            "versions": [version.to_dict() for version in self.versions]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileManifest':
        """Create from dictionary after deserialization."""
        manifest = cls(
            file_id=data.get("file_id", str(uuid.uuid4())),
            original_filename=data.get("original_filename", ""),
            total_size=data.get("total_size", 0),
            chunk_size=data.get("chunk_size", 0)
        )
        
        manifest.created_at = data.get("created_at", time.time())
        manifest.updated_at = data.get("updated_at", manifest.created_at)
        
        # Handle old format (without versions) for backward compatibility
        if "chunks" in data and "versions" not in data:
            chunks = [ChunkInfo.from_dict(chunk) for chunk in data.get("chunks", [])]
            manifest.add_version(chunks, "Migrated from old format")
        else:
            for version_data in data.get("versions", []):
                version = FileVersion.from_dict(version_data)
                manifest.versions.append(version)
        
        return manifest

class MetadataManager:
    """Manages file manifests for the storage system."""

    def __init__(self, metadata_dir: str = METADATA_DIR):
        self.metadata_dir = metadata_dir
        os.makedirs(self.metadata_dir, exist_ok=True)
        print(f"MetadataManager initialized. Manifests stored in: {os.path.abspath(self.metadata_dir)}")

    def generate_file_id(self) -> str:
        """Generates a unique file ID."""
        return str(uuid.uuid4())

    def _get_manifest_path(self, file_id: str) -> str:
        """Constructs the path to a manifest file."""
        # Basic sanitization to prevent path traversal issues
        safe_file_id = "".join(c for c in file_id if c.isalnum() or c in ('-', '_'))
        if not safe_file_id:
            raise ValueError("Invalid file_id format.")
        return os.path.join(self.metadata_dir, f"{safe_file_id}.json")

    def save_manifest(self, manifest: FileManifest):
        """Saves a file manifest to a JSON file."""
        path = self._get_manifest_path(manifest.file_id)
        try:
            manifest_dict = manifest.to_dict()
            with open(path, 'w') as f:
                json.dump(manifest_dict, f, indent=4)
            print(f"Saved manifest for file '{manifest.original_filename}' (ID: {manifest.file_id}) to {path}")
        except IOError as e:
            print(f"Error saving manifest file {path}: {e}")
            raise
        except Exception as e: # Catch potential serialization errors
             print(f"Error serializing manifest data for {path}: {e}")
             raise

    def load_manifest(self, file_id: str) -> Optional[FileManifest]:
        """Loads a file manifest from its JSON file."""
        path = self._get_manifest_path(file_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # Check if the data is a dictionary as expected
            if not isinstance(data, dict):
                print(f"Error: Manifest file {path} contains invalid format (not a dictionary)")
                return None
                
            # Check for required fields
            if not all(key in data for key in ["original_filename", "total_size", "chunk_size"]):
                print(f"Error: Manifest file {path} is missing required fields")
                return None
            
            # Reconstruct the FileManifest object
            try:
                manifest = FileManifest.from_dict(data)
                return manifest
            except (KeyError, TypeError, ValueError) as e:
                print(f"Error reconstructing manifest from {path}: {e}")
                return None
                
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading or parsing manifest file {path}: {e}")
            return None

    def delete_manifest(self, file_id: str) -> bool:
        """Deletes a manifest file."""
        path = self._get_manifest_path(file_id)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Deleted manifest file: {path}")
                return True
            except OSError as e:
                print(f"Error deleting manifest file {path}: {e}")
                return False
        else:
            print(f"Manifest file not found for deletion: {path}")
            return False # Indicate file didn't exist
    
    def list_manifests(self) -> List[Tuple[str, str]]:
        """Lists available manifests (file_id, original_filename)."""
        manifests = []
        try:
            for filename in os.listdir(self.metadata_dir):
                # Skip users.json as it's not a file manifest
                if filename == "users.json":
                    continue
                    
                if filename.endswith(".json"):
                    file_id = filename[:-5] # Remove .json extension
                    manifest = self.load_manifest(file_id)
                    if manifest and hasattr(manifest, 'file_id') and hasattr(manifest, 'original_filename'):
                        manifests.append((manifest.file_id, manifest.original_filename))
                    else:
                         print(f"Warning: Found invalid manifest file: {filename}")
        except OSError as e:
             print(f"Error listing manifest directory {self.metadata_dir}: {e}")
        return manifests 