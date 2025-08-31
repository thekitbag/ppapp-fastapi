from typing import Optional, Dict, Any


class AppException(Exception):
    """Base application exception."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppException):
    """Validation error exception."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class NotFoundError(AppException):
    """Resource not found exception."""
    
    def __init__(self, resource: str, resource_id: str):
        message = f"{resource} with id '{resource_id}' not found"
        super().__init__(message, status_code=404)


class ConflictError(AppException):
    """Resource conflict exception."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=409, details=details)