"""
API metadata endpoints.

Provides version information, API status, and operational metrics.
"""

import time
from datetime import datetime, timezone
from fastapi import APIRouter
from config import settings
from utils.circuit_breaker import CircuitState, db_circuit_breaker

router = APIRouter()

# Track application start time for uptime calculation
_START_TIME = time.time()


@router.get(
    "/version",
    summary="Get API Version",
    description="Returns API version information, build details, and environment.",
    response_description="API version and build information",
    tags=["Meta"]
)
async def get_version():
    """
    Get API version and build information.
    
    Returns version number, API version, environment, and build date.
    Useful for debugging and ensuring correct deployment version.
    """
    return {
        "version": settings.app_version,
        "api_version": "v1",
        "environment": settings.environment,
        "build_date": settings.build_date,
        "app_name": settings.app_name,
    }


@router.get(
    "/status",
    summary="Get API Status",
    description="Returns detailed operational status of the API and its components.",
    response_description="Current API status and component health",
    tags=["Meta"]
)
async def get_status():
    """
    Get detailed API status.
    
    Provides operational status, uptime, and health of individual endpoints.
    Reports real circuit breaker state for connection endpoint.
    Used for monitoring and service health checks.
    """
    # Calculate uptime
    uptime_seconds = int(time.time() - _START_TIME)

    # Reflect real circuit breaker state for the connection endpoint
    cb = db_circuit_breaker
    if cb is None or not settings.circuit_breaker_enabled:
        connection_status = "operational"
    elif cb.state == CircuitState.OPEN:
        connection_status = "degraded"
    elif cb.state == CircuitState.HALF_OPEN:
        connection_status = "recovering"
    else:
        connection_status = "operational"

    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "uptime_seconds": uptime_seconds,
        "uptime_human": _format_uptime(uptime_seconds),
        "endpoints": {
            "health": "operational",
            "connections": connection_status,
            "meta": "operational",
        },
        "features": {
            "rate_limiting": settings.rate_limit_enabled,
            "circuit_breaker": settings.circuit_breaker_enabled,
        }
    }


def _format_uptime(seconds: int) -> str:
    """
    Format uptime seconds into human-readable string.
    
    Args:
        seconds: Uptime in seconds
        
    Returns:
        Human-readable uptime string (e.g., "2d 3h 45m")
    """
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m"
    
    days = hours // 24
    return f"{days}d {hours % 24}h {minutes % 60}m"
