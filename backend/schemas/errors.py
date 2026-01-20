from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Standardized error codes for database connection failures.
    
    These codes allow the frontend to programmatically handle specific error types
    while keeping user-facing messages human-readable.
    """
    
    # Authentication & Authorization
    AUTH_FAILED = "AUTH_FAILED"
    
    # Database issues
    DATABASE_NOT_FOUND = "DATABASE_NOT_FOUND"
    
    # Network & Connectivity
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    
    # SSL/TLS issues
    SSL_ERROR = "SSL_ERROR"
    
    # Validation errors
    INVALID_URL = "INVALID_URL"
    
    # Catch-all for unexpected errors
    UNKNOWN = "UNKNOWN"


class ConnectionResult(BaseModel):
    """Structured result from connection test operations.
    
    Used internally by the service layer to return consistent results
    that include success status, message, and optional error code.
    """
    
    success: bool = Field(
        ...,
        description="Whether the connection test succeeded"
    )
    message: str = Field(
        ...,
        description="Human-readable message describing the result"
    )
    error_code: Optional[ErrorCode] = Field(
        default=None,
        description="Standardized error code for programmatic handling (None on success)"
    )
