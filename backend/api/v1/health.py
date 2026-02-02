"""Health check endpoint for database connectivity monitoring."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from schemas.health import HealthCheckResponse, DatabaseHealthStatus
from utils.connection_resilience import health_monitor, ConnectionState
from config import settings

# Configure logger
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="""
Check the health of the API and database connectivity.

**Response Behavior:**
- Always returns HTTP 200 to indicate the API is responsive
- Database status is reported in the nested `database` object
- Latency is measured and reported in milliseconds

**Database Status Values:**
- `connected`: Database is reachable and responding
- `unavailable`: Database connection failed
- `unknown`: No connection URL configured or never checked
    """,
    responses={
        200: {
            "description": "Health check completed (API is always healthy if responding)",
            "model": HealthCheckResponse
        }
    },
    operation_id="health_check",
    tags=["Health"]
)
async def health_check(
    db_url: Optional[str] = Query(
        default=None,
        description="Database URL to check (uses default if not provided)",
        include_in_schema=False  # Hide from OpenAPI to avoid credential exposure
    )
) -> HealthCheckResponse:
    """
    Perform health check including database connectivity test.
    
    Args:
        db_url: Optional database URL to check. If not provided, uses 
                configured health check URL or returns 'unknown' status.
    
    Returns:
        HealthCheckResponse with API status and database health details.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Determine which URL to check
    check_url = db_url or getattr(settings, 'health_check_db_url', None)
    
    if not check_url:
        # No URL configured - return unknown status
        logger.debug("Health check: No database URL configured")
        return HealthCheckResponse(
            status="ok",
            timestamp=timestamp,
            database=DatabaseHealthStatus(
                status="unknown",
                latency_ms=None,
                consecutive_failures=health_monitor.consecutive_failures
            )
        )
    
    # Perform health check with timing
    start_time = time.perf_counter()
    
    try:
        result = health_monitor.check_connection(
            url=check_url,
            timeout=getattr(settings, 'health_check_timeout', 2)
        )
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        
        if result.success:
            logger.debug(f"Health check: Database connected ({elapsed_ms}ms)")
            return HealthCheckResponse(
                status="ok",
                timestamp=timestamp,
                database=DatabaseHealthStatus(
                    status="connected",
                    latency_ms=elapsed_ms,
                    consecutive_failures=0
                )
            )
        else:
            logger.warning(f"Health check: Database unavailable ({elapsed_ms}ms)")
            return HealthCheckResponse(
                status="ok",
                timestamp=timestamp,
                database=DatabaseHealthStatus(
                    status="unavailable",
                    latency_ms=elapsed_ms,
                    consecutive_failures=health_monitor.consecutive_failures
                )
            )
            
    except Exception as e:
        # Catch any unexpected errors - health endpoint should never fail
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"Health check unexpected error: {type(e).__name__}")
        
        return HealthCheckResponse(
            status="ok",
            timestamp=timestamp,
            database=DatabaseHealthStatus(
                status="unavailable",
                latency_ms=elapsed_ms,
                consecutive_failures=health_monitor.consecutive_failures
            )
        )
