from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ConnectionRequest(BaseModel):
    """Request schema for testing database connection."""
    
    connection_url: str = Field(
        ..., 
        min_length=1, 
        description="The PostgreSQL connection URL string",
        json_schema_extra={
            "example": "postgresql://user:password@localhost:5432/mydatabase"
        }
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "connection_url": "postgresql://user:password@localhost:5432/mydatabase"
            }
        }
    )


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
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Connection failed: Authentication error. Please verify your username, password, and access permissions."
            }
        }
    )
