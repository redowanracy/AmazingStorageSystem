import uuid
import time
import json
import os
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime

# Directory to store user data
USERS_DIR = "metadata/users"

class UserRole(Enum):
    USER = "user"
    # PROVIDER = "provider"
    # ADMIN = "admin"

# Remove PaymentStatus enum
# class PaymentStatus(Enum): ...

class User:
    def __init__(self, 
                 username: str, 
                 email: str, 
                 password_hash: str,
                 user_id: str = None,
                 role: UserRole = UserRole.USER):
                 # Remove payment and provider attributes
                 # payment_status: PaymentStatus = PaymentStatus.UNPAID,
                 # payment_expiry: int = 0,
                 # provider_details: Dict = None):
        
        self.user_id = user_id or str(uuid.uuid4())
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role # Keep role, but it will always be USER
        # Remove payment and provider attributes assignment
        # self.payment_status = payment_status
        # self.payment_expiry = payment_expiry
        self.created_at = int(time.time())
        # self.provider_details = provider_details or {}
        
    # Remove is_provider method
    # def is_provider(self): ...
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary for storage"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "role": self.role.value, # Will always be 'user'
            # Remove payment/provider fields
            # "payment_status": self.payment_status.value,
            # "payment_expiry": self.payment_expiry,
            "created_at": self.created_at
            # "provider_details": self.provider_details
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create user object from dictionary data"""
        return cls(
            user_id=data.get("user_id"),
            username=data.get("username"),
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            role=UserRole(data.get("role", "user")) # Still read role, but should only be 'user'
            # Remove payment/provider fields
            # payment_status=PaymentStatus(data.get("payment_status", "unpaid")),
            # payment_expiry=data.get("payment_expiry", 0),
            # provider_details=data.get("provider_details", {})
        )
        
    def save(self):
        """Save user to storage"""
        os.makedirs(USERS_DIR, exist_ok=True)
        path = os.path.join(USERS_DIR, f"{self.user_id}.json")
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)
            
    # Remove has_active_subscription method
    # def has_active_subscription(self) -> bool: ...
                
    # Remove apply_as_provider method
    # def apply_as_provider(self, provider_details: Dict[str, Any]) -> bool: ...
        
    # Remove process_payment method
    # def process_payment(self, amount: float, payment_method: str = "bkash", transaction_id: str = None) -> bool: ...


class UserManager:
    def __init__(self, data_dir="metadata"):
        self.users_file = os.path.join(data_dir, "users.json")
        self.users = {}
        self._ensure_data_dir(data_dir)
        self._load_users()
        
    def _ensure_data_dir(self, data_dir):
        """Ensure data directory exists"""
        os.makedirs(data_dir, exist_ok=True)
        
    def _load_users(self):
        """Load users from file"""
        if not os.path.exists(self.users_file):
            return
            
        try:
            with open(self.users_file, 'r') as f:
                user_dicts = json.load(f)
                
            for user_dict in user_dicts:
                user = User.from_dict(user_dict)
                self.users[user.user_id] = user
        except Exception as e:
            print(f"Error loading users: {e}")
            
    def _save_users(self):
        """Save users to file"""
        try:
            user_dicts = [user.to_dict() for user in self.users.values()]
            with open(self.users_file, 'w') as f:
                json.dump(user_dicts, f, indent=2)
        except Exception as e:
            print(f"Error saving users: {e}")
            
    def get_all_users(self):
        """Get all users"""
        return list(self.users.values())
        
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        return self.users.get(user_id)
        
    def get_user_by_username(self, username):
        """Get user by username"""
        for user in self.users.values():
            if user.username.lower() == username.lower():
                return user
        return None
        
    def save_user(self, user):
        """Save or update a user"""
        self.users[user.user_id] = user
        self._save_users()
        
    def delete_user(self, user_id):
        """Delete a user"""
        if user_id in self.users:
            del self.users[user_id]
            self._save_users()
            return True
        return False
        
    # Remove get_providers method
    # def get_providers(self):
    #    """Get all provider users"""
    #    return [user for user in self.users.values() if user.is_provider()]