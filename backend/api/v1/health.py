"""Health check endpoint for database connectivity monitoring."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas.health import HealthCheckResponse
from utils.connection_resilience import health_monitor
from config import get_settings

# Configure logger
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=200,
    summary="Health Check",
    description="""
Check the health of the API and database connectivity.

**Response Behavior:**
- Always returns HTTP 200 to indicate the API is responsive
- Database status is reported in the nested `database` object
- Latency is measured and reported in milliseconds

**Database Status Values:**
- `healthy`: Database is reachable and responding
- `unhealthy`: Database connection failed
- `not_configured`: No connection URL configured

**System Status Values:**
- `ok`: System is healthy (API responsive, database healthy or not configured)
- `degraded`: Database is configured but unavailable

**Configuration:**
Set `HEALTH_CHECK_DB_URL` environment variable to enable database health checks.
    """,
    responses={
        200: {
            "description": "Health check completed - endpoint always returns 200",
            "model": HealthCheckResponse
        }
    },
    operation_id="health_check",
    tags=["Health"]
)
async def health_check() -> JSONResponse:
    """
    Perform health check including database connectivity test.
    
    This endpoint NEVER throws exceptions and ALWAYS returns HTTP 200.
    All errors are caught and converted to appropriate status responses.
    
    Returns:
        JSONResponse with status=200 containing health status
    """
    try:
        # Get timestamp in ISO 8601 format
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Get settings safely
        try:
            settings = get_settings()
            check_url = settings.health_check_db_url
        except Exception as e:
            # If settings fail to load, return degraded status
            logger.error(f"Failed to load settings: {type(e).__name__}", exc_info=False)
            return JSONResponse(
                status_code=200,
                content={
                    "status": "degraded",
                    "timestamp": timestamp,
                    "database": {
                        "configured": False,
                        "status": "not_configured",
                        "latency_ms": None
                    }
                }
            )
        
        # Check if database URL is configured
        if not check_url:
            logger.debug("Health check: No database URL configured")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "timestamp": timestamp,
                    "database": {
                        "configured": False,
                        "status": "not_configured",
                        "latency_ms": None
                    }
                }
            )
        
        # Database URL is configured - perform health check
        start_time = time.perf_counter()
        
        try:
            result = await health_monitor.check_connection(
                url=check_url,
                timeout=settings.health_check_timeout
            )
            
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            if result.success:
                logger.debug(f"Health check: Database healthy ({elapsed_ms}ms)")
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "ok",
                        "timestamp": timestamp,
                        "database": {
                            "configured": True,
                            "status": "healthy",
                            "latency_ms": elapsed_ms
                        }
                    }
                )
            else:
                logger.warning(f"Health check: Database unhealthy ({elapsed_ms}ms)")
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "degraded",
                        "timestamp": timestamp,
                        "database": {
                            "configured": True,
                            "status": "unhealthy",
                            "latency_ms": elapsed_ms  # Report actual elapsed even on failure
                        }
                    }
                )
                
        except Exception as e:
            # Catch ANY exception during health check
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Health check error: {type(e).__name__}", exc_info=False)

            return JSONResponse(
                status_code=200,
                content={
                    "status": "degraded",
                    "timestamp": timestamp,
                    "database": {
                        "configured": True,
                        "status": "unhealthy",
                        "latency_ms": elapsed_ms  # Report actual elapsed even on exception
                    }
                }
            )
    
    except Exception as e:
        # Ultimate fallback - catch EVERYTHING
        logger.error(f"Critical health check error: {type(e).__name__}", exc_info=False)
        
        # Return a basic response even if timestamp generation failed
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
        except:
            timestamp = "1970-01-01T00:00:00"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "degraded",
                "timestamp": timestamp,
                "database": {
                    "configured": False,
                    "status": "not_configured",
                    "latency_ms": None
                }
            }
        )
