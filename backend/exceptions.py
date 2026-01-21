"""Custom exceptions for the SequelSpeak backend API."""

from typing import Optional
from fastapi import HTTPException, status
from schemas.errors import ErrorCode


class DatabaseConnectionError(HTTPException):
    """
    Custom exception for database connection errors.
    
    This exception is raised when database connection validation or
    connection attempts fail. It provides structured error information
    including a human-readable message and a machine-readable error code.
    
    Attributes:
        detail: Human-readable error message
        error_code: Standardized error code for programmatic handling
        status_code: HTTP status code (always 400 for connection errors)
    """
    
    def __init__(
        self,
        detail: str,
        error_code: Optional[ErrorCode] = None
    ):
        """
        Initialize a DatabaseConnectionError.
        
        Args:
            detail: Human-readable error message explaining the failure
            error_code: Optional ErrorCode enum value for programmatic handling
        """
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
        self.error_code = error_code
