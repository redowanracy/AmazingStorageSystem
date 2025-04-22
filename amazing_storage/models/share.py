import os
import time
import json
import uuid
import hashlib
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Directory to store share data
SHARES_DIR = "metadata/shares"
os.makedirs(SHARES_DIR, exist_ok=True)

class ShareLink:
    """Represents a time-limited share link for a file."""
    
    def __init__(self, 
                 file_id: str,
                 creator_id: str,
                 expiry_hours: int = 24,
                 share_id: str = None,
                 download_limit: int = 0,
                 downloads: int = 0,
                 created_at: int = None,
                 password_hash: str = None,
                 notes: str = "",
                 ):
        """
        Initialize a new share link.
        
        Args:
            file_id: The ID of the file to share
            creator_id: The ID of the user creating the share
            expiry_hours: Number of hours until the share expires (0 = never)
            share_id: Unique ID for the share (generated if not provided)
            download_limit: Max number of downloads allowed (0 = unlimited)
            downloads: Current download count
            created_at: Timestamp when the share was created
            password_hash: Optional password hash for the share
            notes: Optional notes about the share
        """
        self.file_id = file_id
        self.creator_id = creator_id
        self.share_id = share_id or str(uuid.uuid4())
        self.access_token = self._generate_token()
        self.created_at = created_at or int(time.time())
        self.expires_at = self.created_at + (expiry_hours * 3600) if expiry_hours > 0 else 0
        self.download_limit = download_limit
        self.downloads = downloads
        self.password_hash = password_hash
        self.notes = notes
    
    def _generate_token(self) -> str:
        """Generate a secure random token for the share link."""
        return secrets.token_urlsafe(32)
    
    def is_valid(self) -> bool:
        """Check if the share link is still valid."""
        # Check expiry if set
        if self.expires_at > 0 and time.time() > self.expires_at:
            return False
        
        # Check download limit if set
        if self.download_limit > 0 and self.downloads >= self.download_limit:
            return False
            
        return True
    
    def increment_downloads(self):
        """Increment the download counter and save."""
        self.downloads += 1
        self.save()
    
    def set_password(self, password: str):
        """Set a password for the share link."""
        salt = secrets.token_hex(8)
        password_hash = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
        self.password_hash = f"{salt}${password_hash}"
        self.save()
    
    def verify_password(self, password: str) -> bool:
        """Verify the provided password against the stored hash."""
        if not self.password_hash:
            return True  # No password set
            
        salt, stored_hash = self.password_hash.split('$')
        password_hash = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
        return password_hash == stored_hash
    
    def get_share_url(self, base_url: str) -> str:
        """Generate the full share URL."""
        return f"{base_url}/share/{self.share_id}/{self.access_token}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "share_id": self.share_id,
            "file_id": self.file_id, 
            "creator_id": self.creator_id,
            "access_token": self.access_token,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "download_limit": self.download_limit,
            "downloads": self.downloads,
            "password_hash": self.password_hash,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShareLink':
        """Create from dictionary."""
        return cls(
            file_id=data.get("file_id"),
            creator_id=data.get("creator_id"),
            share_id=data.get("share_id"),
            expiry_hours=0,  # Not used when loading from dict
            download_limit=data.get("download_limit", 0),
            downloads=data.get("downloads", 0),
            created_at=data.get("created_at"),
            password_hash=data.get("password_hash"),
            notes=data.get("notes", "")
        )
    
    def save(self):
        """Save share data to disk."""
        path = os.path.join(SHARES_DIR, f"{self.share_id}.json")
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def delete(self) -> bool:
        """Delete the share file."""
        path = os.path.join(SHARES_DIR, f"{self.share_id}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


class ShareManager:
    """Manages file shares in the system."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        """Initialize the share manager."""
        self.base_url = base_url
    
    def create_share(self, file_id: str, creator_id: str, expiry_hours: int = 24, 
                    download_limit: int = 0, password: str = None, notes: str = "") -> ShareLink:
        """Create a new share link for a file."""
        share = ShareLink(
            file_id=file_id,
            creator_id=creator_id,
            expiry_hours=expiry_hours,
            download_limit=download_limit,
            notes=notes
        )
        
        if password:
            share.set_password(password)
        else:
            share.save()
            
        return share
    
    def get_share(self, share_id: str, access_token: str = None) -> Optional[ShareLink]:
        """Get a share by ID and optionally validate its access token."""
        path = os.path.join(SHARES_DIR, f"{share_id}.json")
        if not os.path.exists(path):
            return None
            
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                
            share = ShareLink.from_dict(data)
            
            # Validate access token if provided
            if access_token and share.access_token != access_token:
                return None
                
            return share
            
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading share {share_id}: {e}")
            return None
    
    def list_shares_by_creator(self, creator_id: str) -> List[ShareLink]:
        """List all shares created by a specific user."""
        shares = []
        for filename in os.listdir(SHARES_DIR):
            if not filename.endswith(".json"):
                continue
                
            path = os.path.join(SHARES_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                if data.get("creator_id") == creator_id:
                    share = ShareLink.from_dict(data)
                    shares.append(share)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error reading share file {filename}: {e}")
        
        return shares
    
    def list_shares_by_file(self, file_id: str) -> List[ShareLink]:
        """List all shares for a specific file."""
        shares = []
        for filename in os.listdir(SHARES_DIR):
            if not filename.endswith(".json"):
                continue
                
            path = os.path.join(SHARES_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                if data.get("file_id") == file_id:
                    share = ShareLink.from_dict(data)
                    shares.append(share)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error reading share file {filename}: {e}")
        
        return shares
    
    def delete_share(self, share_id: str, creator_id: str = None) -> bool:
        """
        Delete a share by ID. If creator_id is provided, 
        ensures only the creator can delete it.
        """
        share = self.get_share(share_id)
        if not share:
            return False
            
        if creator_id and share.creator_id != creator_id:
            return False
            
        return share.delete()
    
    def cleanup_expired_shares(self) -> int:
        """Delete all expired shares and return count of deleted shares."""
        count = 0
        current_time = time.time()
        
        for filename in os.listdir(SHARES_DIR):
            if not filename.endswith(".json"):
                continue
                
            path = os.path.join(SHARES_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                # Check if share is expired by time
                expires_at = data.get("expires_at", 0)
                if expires_at > 0 and current_time > expires_at:
                    os.remove(path)
                    count += 1
                    continue
                
                # Check if share is expired by download count
                download_limit = data.get("download_limit", 0)
                downloads = data.get("downloads", 0)
                if download_limit > 0 and downloads >= download_limit:
                    os.remove(path)
                    count += 1
                    
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"Error processing share file {filename}: {e}")
        
        return count 