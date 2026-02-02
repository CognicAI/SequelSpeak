"""Response schemas for health endpoint."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class DatabaseHealthStatus(BaseModel):
    """Database connectivity status within health check response."""
    
    status: Literal["connected", "unavailable", "unknown"] = Field(
        ...,
        description="Current database connection status"
    )
    latency_ms: Optional[int] = Field(
        default=None,
        description="Database response time in milliseconds (null if unavailable)"
    )
    consecutive_failures: int = Field(
        default=0,
        description="Number of consecutive connection failures"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "connected",
                "latency_ms": 15,
                "consecutive_failures": 0
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Response schema for health check endpoint.
    
    The endpoint always returns HTTP 200 to indicate the API is responsive.
    Database health is reported in the nested 'database' object.
    """
    
    status: Literal["ok"] = Field(
        default="ok",
        description="API status - always 'ok' if endpoint responds"
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
                    "summary": "Database Connected",
                    "description": "Healthy response when database is reachable",
                    "value": {
                        "status": "ok",
                        "timestamp": "2026-02-02T16:15:00+00:00",
                        "database": {
                            "status": "connected",
                            "latency_ms": 15,
                            "consecutive_failures": 0
                        }
                    }
                },
                {
                    "summary": "Database Unavailable",
                    "description": "Response when database connection fails",
                    "value": {
                        "status": "ok",
                        "timestamp": "2026-02-02T16:15:00+00:00",
                        "database": {
                            "status": "unavailable",
                            "latency_ms": 2000,
                            "consecutive_failures": 3
                        }
                    }
                },
                {
                    "summary": "Database Unknown",
                    "description": "Response when no database URL is configured",
                    "value": {
                        "status": "ok",
                        "timestamp": "2026-02-02T16:15:00+00:00",
                        "database": {
                            "status": "unknown",
                            "latency_ms": None,
                            "consecutive_failures": 0
                        }
                    }
                }
            ]
        }
    )

