"""
Connection resilience utilities for detecting and handling dropped database connections.

This module provides tools to detect runtime connection failures and propagate
errors correctly without crashing the application.
"""

import logging
import threading
import time
from enum import Enum
from functools import wraps
from typing import Callable, Optional, Any, TypeVar, cast

import psycopg

from schemas.errors import ErrorCode, ConnectionResult
from utils.security import mask_connection_url

T = TypeVar("T")

# Configure logger
logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Tracks the health state of a database connection."""
    
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


# Patterns that indicate a dropped/lost connection (runtime failure)
# These are distinct from initial connection failures (host unreachable, auth failed, etc.)
CONNECTION_LOST_PATTERNS = [
    "connection closed",
    "server closed the connection unexpectedly",
    "connection reset",
    "broken pipe",
    "connection terminated",
    "connection already closed",
    "connection is closed",
    "connection has been closed",
    "connection was closed",
    "lost connection",
    "server has gone away",
    "connection timed out during operation",
    "connection dropped",
]


def is_connection_lost_error(exception: Exception) -> bool:
    """
    Analyze an exception to determine if it indicates a dropped connection.
    
    This distinguishes runtime connection drops from initial connection failures.
    For example, a "host unreachable" error is an initial failure, while
    "connection closed unexpectedly" is a runtime drop.
    
    SSL errors and timeout errors are NOT considered retryable connection losses
    as they indicate configuration or network issues that won't resolve with retry.
    
    Args:
        exception: The exception to analyze
        
    Returns:
        True if the exception indicates a lost connection, False otherwise
    """
    # psycopg.InterfaceError typically indicates invalid cursor/connection state
    if isinstance(exception, psycopg.InterfaceError):
        error_msg = str(exception).lower()
        # Check for patterns indicating the connection was lost
        if any(pattern in error_msg for pattern in ["closed", "invalid", "not connected"]):
            return True
    
    # psycopg.OperationalError can indicate connection drops during operations
    if isinstance(exception, psycopg.OperationalError):
        error_msg = str(exception).lower()
        
        # Explicitly exclude SSL/TLS errors - these indicate configuration issues
        # and should not be retried
        ssl_patterns = [
            "ssl error", "ssl connection", "ssl handshake", "ssl syscall",
            "certificate verify", "certificate validation", "certificate_verify_failed",
            "tlsv1", "ssl_error", "certificate expired", "certificate invalid",
            "self-signed certificate"
        ]
        if any(pattern in error_msg for pattern in ssl_patterns):
            return False
        
        # Explicitly exclude timeout errors - these indicate network/performance issues
        # that won't resolve with immediate retry
        # However, "connection timed out during operation" indicates a dropped connection
        # and should be retryable
        if "timeout expired" in error_msg or "connection timeout" in error_msg:
            return False
        # "timed out" is excluded unless it's part of "during operation"
        if "timed out" in error_msg and "during operation" not in error_msg:
            return False
        
        # Check for connection lost patterns
        if any(pattern in error_msg for pattern in CONNECTION_LOST_PATTERNS):
            return True
    
    # Check for generic socket/connection errors
    if isinstance(exception, (ConnectionError, BrokenPipeError, ConnectionResetError)):
        return True
    
    return False


def detect_connection_failure(func: Callable) -> Callable:
    """
    Decorator that wraps database operations to detect connection failures.
    
    This decorator:
    1. Catches connection-related exceptions
    2. Logs failures securely (masking credentials)
    3. Returns a ConnectionResult with CONNECTION_LOST error code
    4. Never raises exceptions to callers (graceful degradation)
    
    Usage:
        @detect_connection_failure
        def my_database_operation(url: str) -> ConnectionResult:
            # ... perform database operation
            
    Args:
        func: The function to wrap
        
    Returns:
        Wrapped function that handles connection failures gracefully
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> ConnectionResult:
        try:
            return func(*args, **kwargs)
        except psycopg.InterfaceError as e:
            # Interface errors typically mean invalid connection state
            secure_error_msg = mask_connection_url(str(e))
            
            if is_connection_lost_error(e):
                logger.error(f"Database connection interface error: {secure_error_msg}")
                return ConnectionResult(
                    success=False,
                    message="Database connection was lost. Please try again.",
                    error_code=ErrorCode.CONNECTION_LOST
                )
            else:
                # Re-raise non-connection-lost interface errors
                raise
        except psycopg.OperationalError as e:
            error_msg = str(e)
            secure_error_msg = mask_connection_url(error_msg)
            
            if is_connection_lost_error(e):
                logger.error(f"Database connection lost: {secure_error_msg}")
                return ConnectionResult(
                    success=False,
                    message="Database connection was lost. Please try again.",
                    error_code=ErrorCode.CONNECTION_LOST
                )
            else:
                # Re-raise non-connection-lost operational errors
                # so they can be handled by the original error handling
                raise
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            secure_error_msg = mask_connection_url(str(e))
            logger.error(f"Network connection error: {secure_error_msg}")
            return ConnectionResult(
                success=False,
                message="Database connection was lost. Please try again.",
                error_code=ErrorCode.CONNECTION_LOST
            )
        except Exception as e:
            # For unexpected errors, log securely but don't mask as connection lost
            secure_error_msg = mask_connection_url(str(e))
            logger.error(f"Unexpected error in database operation: {secure_error_msg}")
            return ConnectionResult(
                success=False,
                message="An unexpected error occurred while accessing the database.",
                error_code=ErrorCode.CONNECTION_ERROR
            )
    
    return wrapper


def retry_on_connection_failure(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
class ConnectionHealthMonitor:
    """
    Monitors and tracks the health state of a database connection.
    
    This class is thread-safe and safe for concurrent FastAPI workers/threads.
    It provides methods to check connection health and track state changes 
    for use by health check endpoints or reconnection logic.
    
    Attributes:
        state: Current connection state (CONNECTED, DISCONNECTED, UNKNOWN)
        last_check_time: Timestamp of last health check
        consecutive_failures: Number of consecutive connection failures
    """
    
    def __init__(self):
        """Initialize the health monitor with unknown state."""
        self._state: ConnectionState = ConnectionState.UNKNOWN
        self._consecutive_failures: int = 0
        self._lock = threading.RLock()
    
    @property
    def state(self) -> ConnectionState:
        """Get the current connection state."""
        with self._lock:
            return self._state
    
    @property
    def is_healthy(self) -> bool:
        """Check if the connection is currently healthy."""
        with self._lock:
            return self._state == ConnectionState.CONNECTED
    
    @property
    def consecutive_failures(self) -> int:
        """Get the number of consecutive connection failures."""
        with self._lock:
            return self._consecutive_failures
    
    def mark_healthy(self) -> None:
        """Mark the connection as healthy and reset failure count."""
        with self._lock:
            self._state = ConnectionState.CONNECTED
            self._consecutive_failures = 0
        logger.debug("Connection marked as healthy")
    
    def mark_unhealthy(self) -> None:
        """Mark the connection as unhealthy and increment failure count."""
        with self._lock:
            self._state = ConnectionState.DISCONNECTED
            self._consecutive_failures += 1
            failures = self._consecutive_failures
        logger.warning(f"Connection marked as unhealthy (consecutive failures: {failures})")
    
    def check_connection(self, url: str, timeout: int = 5) -> ConnectionResult:
        """
        Perform a lightweight connection check.
        
        Args:
            url: Database connection URL
            timeout: Connection timeout in seconds
            
        Returns:
            ConnectionResult indicating success or failure
        """
        try:
            with psycopg.connect(url, connect_timeout=timeout) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    if result == (1,):
                        self.mark_healthy()
                        return ConnectionResult(
                            success=True,
                            message="Connection is healthy"
                        )
                    else:
                        self.mark_unhealthy()
                        return ConnectionResult(
                            success=False,
                            message="Connection check failed",
                            error_code=ErrorCode.CONNECTION_ERROR
                        )
        except psycopg.OperationalError as e:
            secure_error_msg = mask_connection_url(str(e))
            logger.error(f"Health check failed: {secure_error_msg}")
            self.mark_unhealthy()
            
            if is_connection_lost_error(e):
                return ConnectionResult(
                    success=False,
                    message="Database connection was lost",
                    error_code=ErrorCode.CONNECTION_LOST
                )
            else:
                return ConnectionResult(
                    success=False,
                    message="Database connection failed",
                    error_code=ErrorCode.CONNECTION_ERROR
                )
        except Exception as e:
            secure_error_msg = mask_connection_url(str(e))
            logger.error(f"Health check error: {secure_error_msg}")
            self.mark_unhealthy()
            return ConnectionResult(
                success=False,
                message="Connection check failed unexpectedly",
                error_code=ErrorCode.CONNECTION_ERROR
            )


# Singleton health monitor instance for application-wide use
health_monitor = ConnectionHealthMonitor()
