import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import session, request, redirect, url_for
from functools import wraps
from ..models.user import User, UserManager
from typing import Optional


class AuthManager:
    def __init__(self):
        self.user_manager = UserManager()
        self.session_timeout = 3600  # 1 hour
        self._ensure_admin_exists()
        
    def _ensure_admin_exists(self):
        """Ensure that an admin user exists"""
        admin = self.user_manager.get_user_by_username("admin")
        if not admin:
            # Create an admin user if none exists
            admin = User(
                username="admin",
                email="admin@amazingstorage.local",
                password_hash=self._hash_password("admin123"),  # Default password, should be changed
            )
            self.user_manager.save_user(admin)
    
    def _hash_password(self, password):
        """Hash a password for storage"""
        salt = secrets.token_hex(16)
        pwdhash = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
        return f"{salt}${pwdhash}"
    
    def verify_password(self, stored_password, provided_password):
        """Verify a password against stored hash"""
        salt, stored_hash = stored_password.split('$')
        pwdhash = hashlib.sha256(salt.encode() + provided_password.encode()).hexdigest()
        return pwdhash == stored_hash
    
    def login(self, username, password):
        """Log in a user"""
        user = self.user_manager.get_user_by_username(username)
        if not user:
            return False
        
        if self.verify_password(user.password_hash, password):
            # Store in session
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['role'] = user.role
            session['login_time'] = datetime.now().timestamp()
            return True
        return False
    
    def logout(self):
        """Log out the current user"""
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('role', None)
        session.pop('login_time', None)
    
    def is_authenticated(self):
        """Check if the current user is authenticated"""
        if 'user_id' not in session:
            return False
        
        # Check session timeout
        if datetime.now().timestamp() - session.get('login_time', 0) > self.session_timeout:
            self.logout()
            return False
        
        # Update login time
        session['login_time'] = datetime.now().timestamp()
        return True
    
    def current_user(self) -> Optional[User]:
        """Get the currently logged-in user based on session data."""
        if not self.is_authenticated():
            return None
        
        return self.user_manager.get_user_by_id(session['user_id'])
    
    def register_user(self, username, email, password, role="user"):
        """Register a new user"""
        # Check if username already exists
        if self.user_manager.get_user_by_username(username):
            return False, "Username already exists"
        
        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=self._hash_password(password),
            role=role,
            payment_status="unpaid",
            provider_details=None
        )
        
        self.user_manager.save_user(user)
        return True, "User registered successfully"
    
    def require_login(self, f):
        """Decorator to require login for a route"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.is_authenticated():
                return redirect(url_for('login', next=request.url))
            return f(*args, **kwargs)
        return decorated_function
    
    def require_admin(self, f):
        """Decorator to require admin role for a route"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.is_authenticated():
                return redirect(url_for('login', next=request.url))
            
            user = self.current_user()
            if user.role != "admin":
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    
    def save_user_data(self):
        """Save all user data"""
        if self.is_authenticated():
            current = self.current_user()
            if current:
                self.user_manager.save_user(current)
                return True
        return False 