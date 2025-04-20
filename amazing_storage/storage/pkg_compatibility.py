"""
Compatibility layer for pkg_resources in Python 3.13+

This module acts as a shim for pkg_resources in newer Python versions
where the module might not be natively available or has compatibility issues.
"""

import sys
import importlib.metadata

# Only patch the system if we can't import pkg_resources
try:
    import pkg_resources
except ImportError:
    print("Creating pkg_resources compatibility layer...")
    
    # Create a mock pkg_resources module
    class PkgResourcesMock:
        def require(self, *args, **kwargs):
            return []
        
        def get_distribution(self, name):
            try:
                return importlib.metadata.distribution(name)
            except importlib.metadata.PackageNotFoundError:
                return None
        
        def resource_exists(self, *args, **kwargs):
            return False
        
        def resource_isdir(self, *args, **kwargs):
            return False
        
        def resource_filename(self, *args, **kwargs):
            return ""
    
    # Insert the mock into sys.modules
    sys.modules['pkg_resources'] = PkgResourcesMock()
    
    print("pkg_resources compatibility layer created.") 