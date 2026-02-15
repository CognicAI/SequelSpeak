"""
Prometheus metrics integration for SequelSpeak backend.

Provides centralized metrics collection with proper cardinality management,
connection pool integration, and production-ready best practices.
"""

import re
import logging
from typing import Optional
from prometheus_client import (
    Counter, 
    Histogram, 
    Gauge, 
    generate_latest, 
    CONTENT_TYPE_LATEST, 
    CollectorRegistry,
    REGISTRY as DEFAULT_REGISTRY
)
from config import settings

logger = logging.getLogger(__name__)

# Custom registry to avoid conflicts with default collectors
# This gives us full control over what metrics are exposed
registry = CollectorRegistry()

# ============================================================================
# Metric Definitions
# ============================================================================

# Application info metric (using Gauge with labels instead of Info for reliability)
app_info = Gauge(
    'sequelspeak_info',
    'Application information',
    ['version', 'environment', 'app_name'],
    registry=registry
)

# HTTP request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    # Buckets optimized for web APIs (50ms to 10s)
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently being processed',
    ['method', 'endpoint'],
    registry=registry
)

# Database connection metrics
active_database_connections = Gauge(
    'active_database_connections',
    'Number of active database connections across all pools',
    registry=registry
)

database_connection_pools = Gauge(
    'database_connection_pools_total',
    'Total number of database connection pools',
    registry=registry
)

# Database error metrics
database_errors_total = Counter(
    'database_errors_total',
    'Total database errors',
    ['error_code'],
    registry=registry
)

# ============================================================================
# Path Template Extraction
# ============================================================================

# Common patterns for dynamic path segments
# These patterns match segments at the end of paths (after the last /)
# to avoid replacing legitimate path component names
PATH_PATTERNS = [
    # UUID v4 pattern (anywhere in path after a /)
    (re.compile(r'/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?=/|$)', re.IGNORECASE), '/{uuid}'),
    # Long numeric IDs (6+ digits, at end or followed by /)
    (re.compile(r'/\d{6,}(?=/|$)'), '/{id}'),
    # Long alphanumeric IDs (12+ chars with at least 3 digits, at end or followed by /)
    # Requires fewer letters, mostly numbers to avoid matching words like "connection"
    (re.compile(r'/(?=(?:[^0-9]*[0-9]){3,})[a-zA-Z0-9]{12,}(?=/|$)'), '/{id}'),
]

def extract_path_template(path: str) -> str:
    """
    Extract a path template from a request path to prevent high-cardinality labels.
    
    Replaces dynamic segments (IDs, UUIDs) with template placeholders to ensure
    metrics don't explode with unique label values.
    
    Examples:
        /api/v1/user/123456 -> /api/v1/user/{id}
        /api/v1/connection/abc123def456 -> /api/v1/connection/{id}
        /api/v1/query/550e8400-e29b-41d4-a716-446655440000 -> /api/v1/query/{uuid}
        /api/v1/health -> /api/v1/health (unchanged)
        /api/v1/connection -> /api/v1/connection (unchanged)
    
    Args:
        path: The request path
        
    Returns:
        Path template with dynamic segments replaced
    """
    template = path
    
    # Apply all patterns in order
    for pattern, replacement in PATH_PATTERNS:
        template = pattern.sub(replacement, template)
    
    return template


# ============================================================================
# Initialization
# ============================================================================

def initialize_metrics() -> None:
    """
    Initialize application metrics.
    
    Sets the application info metric with version and environment.
    Should be called during application startup.
    """
    try:
        # Set application info gauge with labels
        app_info.labels(
            version=getattr(settings, 'app_version', '1.0.0'),
            environment=settings.environment,
            app_name=settings.app_name
        ).set(1)
        logger.info("Prometheus metrics initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Prometheus metrics: {e}")


# ============================================================================
# Integration Functions
# ============================================================================

async def update_connection_pool_metrics() -> None:
    """
    Update connection pool metrics from the pool manager.
    
    Should be called periodically (e.g., every 10 seconds) to keep
    connection metrics up to date.
    
    Gracefully handles errors to prevent metric collection from
    breaking the application.
    """
    try:
        # Import here to avoid circular imports
        from services.connection_pool import pool_manager
        
        # Update active connections gauge
        total_active = await pool_manager.get_total_active_connections()
        active_database_connections.set(total_active)
        
        # Update pool count gauge
        pool_count = await pool_manager.get_pool_count()
        database_connection_pools.set(pool_count)
        
    except Exception as e:
        logger.warning(f"Failed to update connection pool metrics: {e}")


def track_database_error(error_code: str) -> None:
    """
    Track a database error in metrics.
    
    Args:
        error_code: The error code (from DatabaseConnectionError.error_code or similar)
    """
    try:
        database_errors_total.labels(error_code=error_code).inc()
    except Exception as e:
        logger.warning(f"Failed to track database error metric: {e}")


def get_metrics() -> bytes:
    """
    Get Prometheus metrics in text format.
    
    Returns:
        Metrics in Prometheus exposition format
    """
    return generate_latest(registry)


def get_content_type() -> str:
    """
    Get the content type for Prometheus metrics.
    
    Returns:
        Content type string for HTTP response
    """
    return CONTENT_TYPE_LATEST
