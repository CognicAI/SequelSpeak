from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict
from schemas.errors import ErrorCode


class ConnectionRequest(BaseModel):
    """Request schema for testing database connection."""
    
    connection_url: Optional[str] = Field(
        default=None,
        min_length=1, 
        description="The PostgreSQL connection URL string",
        json_schema_extra={
            "example": "postgresql://user:password@localhost:5432/mydatabase"
        }
    )
    
    profile_id: Optional[str] = Field(
        default=None,
        description="The UUID of a saved connection profile"
    )
    
    password: Optional[str] = Field(
        default=None,
        description="The database password (not stored on disk)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "connection_url": "postgresql://user:password@localhost:5432/mydatabase",
                "profile_id": None
            }
        }
    )
    
    from pydantic import model_validator
    
    @model_validator(mode='after')
    def check_at_least_one(self) -> 'ConnectionRequest':
        if not self.connection_url and not self.profile_id:
            raise ValueError('Either connection_url or profile_id must be provided')
        return self


class ConnectionTestResponse(BaseModel):
    """Response schema for successful connection test."""
    
    status: Literal["success"] = Field(
        ..., 
        description="Connection test result status"
    )
    message: str = Field(
        ..., 
        description="Human-readable result message"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "message": "Connection successful!"
            }
        }
    )


class ConnectionErrorDetail(BaseModel):
    """Response schema for connection test errors."""
    
    detail: str = Field(
        ..., 
        description="Error description explaining why the connection failed"
    )
    error_code: Optional[ErrorCode] = Field(
        default=None,
        description="Standardized error code for programmatic error handling"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Connection failed: Authentication error. Please verify your username, password, and access permissions.",
                "error_code": "AUTH_FAILED"
            }
        }
    )
