"""Response schemas for health endpoint."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class DatabaseHealthStatus(BaseModel):
    """Database connectivity status within health check response."""
    
    configured: bool = Field(
        ...,
        description="Whether database URL is configured"
    )
    status: Literal["healthy", "unhealthy", "not_configured"] = Field(
        ...,
        description="Current database connection status"
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Database response time in milliseconds (null if unavailable)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "configured": True,
                "status": "healthy",
                "latency_ms": 15.5
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Response schema for health check endpoint.
    
    The endpoint always returns HTTP 200 to indicate the API is responsive.
    Database health is reported in the nested 'database' object.
    """
    
    status: Literal["ok", "degraded"] = Field(
        ...,
        description="Overall system status - 'ok' if healthy, 'degraded' if database unavailable"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of the health check"
    )
    database: DatabaseHealthStatus = Field(
        ...,
        description="Database connectivity status"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "timestamp": "2026-02-15T10:30:00.000000",
                    "database": {
                        "configured": True,
                        "status": "healthy",
                        "latency_ms": 15.5
                    }
                },
                {
                    "status": "degraded",
                    "timestamp": "2026-02-15T10:30:00.000000",
                    "database": {
                        "configured": True,
                        "status": "unhealthy",
                        "latency_ms": None
                    }
                },
                {
                    "status": "ok",
                    "timestamp": "2026-02-15T10:30:00.000000",
                    "database": {
                        "configured": False,
                        "status": "not_configured",
                        "latency_ms": None
                    }
                }
            ]
        }
    )

