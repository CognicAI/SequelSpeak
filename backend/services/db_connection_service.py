import logging
import psycopg
import re
import asyncio
from typing import Tuple, Optional
from urllib.parse import urlparse, quote_plus, urlunparse
from config import settings
from schemas.errors import ErrorCode, ConnectionResult
from utils.security import mask_connection_url
from utils.input_validator import validate_connection_url
from utils.connection_resilience import is_connection_lost_error, health_monitor
from services.connection_pool import pool_manager

# Configure logger
logger = logging.getLogger(__name__)


class ErrorClassifier:
    """
    Classifies database connection errors into specific error types.
    Uses a data-driven approach to eliminate code duplication.
    """
    
    # Error patterns mapped to (ErrorCode, user_message_template)
    ERROR_PATTERNS = [
        # Authentication errors
        (
            ["password authentication failed", "authentication failed", 
             "no pg_hba.conf entry", "permission denied"],
            ErrorCode.AUTH_FAILED,
            "Connection failed: Authentication error. "
            "Please verify your username, password, and access permissions."
        ),
        # Database not found
        (
            ["does not exist.*database", "database.*does not exist"],
            ErrorCode.DATABASE_NOT_FOUND,
            "Connection failed: The specified database could not be found. "
            "Please verify the database name and that it exists on the server."
        ),
        # SSL/TLS errors
        (
            ["ssl error", "ssl connection", "ssl handshake", "certificate verify",
             "certificate validation", "certificate_verify_failed", "tlsv1",
             "ssl_error", "certificate expired", "certificate invalid", 
             "self-signed certificate"],
            ErrorCode.SSL_ERROR,
            "Connection failed: SSL/TLS certificate error. "
            "Please verify your SSL configuration and certificate validity."
        ),
        # Timeout errors
        (
            ["timeout expired", "timed out", "connection timeout"],
            ErrorCode.TIMEOUT,
            "Connection failed: Connection attempt timed out after {timeout} seconds. "
            "Please verify the host, port, and network connectivity, or try increasing the timeout."
        ),
        # Network/Host errors
        (
            ["ssl syscall", "could not connect to server", "connection refused",
             "could not translate host name", "network is unreachable"],
            ErrorCode.HOST_UNREACHABLE,
            "Connection failed: Unable to reach the database server. "
            "Please verify the host, port, and network connectivity."
        ),
    ]
    
    @classmethod
    def classify_error(cls, error_details: str, timeout: int) -> Tuple[ErrorCode, str]:
        """
        Classifies a database error based on error message patterns.
        
        Args:
            error_details: The error message from the database driver
            timeout: The connection timeout value for message templating
            
        Returns:
            Tuple of (ErrorCode, user_friendly_message)
        """
        details_lower = error_details.lower()
        
        for patterns, error_code, message_template in cls.ERROR_PATTERNS:
            for pattern in patterns:
                # Support regex patterns or simple string matching
                if ".*" in pattern:
                    if re.search(pattern, details_lower):
                        message = message_template.format(timeout=timeout)
                        return error_code, message
                else:
                    if pattern in details_lower:
                        message = message_template.format(timeout=timeout)
                        return error_code, message
        
        # Fallback generic error
        return (
            ErrorCode.CONNECTION_ERROR,
            "Connection failed: Unable to connect to the database. "
            "Please verify your host, port, database name, and credentials."
        )

class DBConnectionService:
    @staticmethod
    def parse_and_verify_url(url: str) -> ConnectionResult:
        """
        Parses the connection URL and validates its structure.
        Performs security validation before structural parsing.
        Returns a ConnectionResult with success status and message.
        """
        # Security validation first - check for injection patterns and dangerous chars
        security_validation = validate_connection_url(url)
        if not security_validation.is_valid:
            logger.warning(f"Security validation failed: {security_validation.error_type}")
            return ConnectionResult(
                success=False,
                message=security_validation.error_message,
                error_code=ErrorCode.INVALID_URL
            )
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or 'postgres' not in parsed.scheme:
                return ConnectionResult(
                    success=False,
                    message="Invalid URL scheme. Must be postgres:// or postgresql://",
                    error_code=ErrorCode.INVALID_URL
                )
            
            # Basic structural check
            if not parsed.netloc:  # Includes host:port or just host
                return ConnectionResult(
                    success=False,
                    message="Invalid URL structure: Host is missing.",
                    error_code=ErrorCode.INVALID_URL
                )

            return ConnectionResult(success=True, message="Valid structure")
        except Exception as e:
            logger.error(f"URL Parsing Error: {str(e)}")
            return ConnectionResult(
                success=False,
                message="Invalid URL format.",
                error_code=ErrorCode.INVALID_URL
            )

    @staticmethod
    async def test_connection(url: str, max_retries: int = 2, initial_delay: float = 1.0) -> ConnectionResult:
        """
        Attempts to connect to the PostgreSQL database using the provided URL with async pooling.
        Automatically retries on transient connection failures with exponential backoff.
        
        Args:
            url: Database connection URL
            max_retries: Maximum number of retry attempts (default 2)
            initial_delay: Initial delay before first retry in seconds (default 1.0)
        
        Returns:
            ConnectionResult indicating success or failure
        """
        retries = 0
        delay = initial_delay
        
        while retries <= max_retries:
            try:
                # Get pool inside retry loop to handle pool exhaustion scenarios
                pool = await pool_manager.get_pool(
                    url,
                    min_size=settings.db_pool_min_size,
                    max_size=settings.db_pool_max_size,
                    timeout=settings.db_pool_timeout
                )
                
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                        result = await cur.fetchone()
                        if result == (1,):
                            health_monitor.mark_healthy()
                            return ConnectionResult(success=True, message="Connection successful!")
                        else:
                            health_monitor.mark_unhealthy()
                            return ConnectionResult(
                                success=False,
                                message="Connection verification query failed.",
                                error_code=ErrorCode.CONNECTION_ERROR
                            )
                        
            except psycopg.OperationalError as e:
                error_details = str(e).strip()
                secure_error_details = mask_connection_url(error_details)
                logger.error(f"Database Connection Failed: {secure_error_details}")

                # Check if this is a connection lost error that should trigger retry
                if is_connection_lost_error(e) and retries < max_retries:
                    retries += 1
                    health_monitor.mark_unhealthy()
                    logger.warning(
                        f"Connection lost. Retrying in {delay:.1f}s... "
                        f"(Attempt {retries}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2.0  # Exponential backoff
                    continue  # Retry the connection

                # If we're here, either it's not retryable or we've exhausted retries
                health_monitor.mark_unhealthy()
                
                # Check if this was a connection lost error (retries exhausted)
                if is_connection_lost_error(e):
                    return ConnectionResult(
                        success=False,
                        message="Database connection was lost. Please try again.",
                        error_code=ErrorCode.CONNECTION_LOST
                    )

                # Classify the error using the ErrorClassifier
                error_code, error_message = ErrorClassifier.classify_error(
                    error_details, 
                    settings.db_connection_timeout
                )
                
                return ConnectionResult(
                    success=False,
                    message=error_message,
                    error_code=error_code
                )

            except Exception as e:
                secure_error_msg = mask_connection_url(str(e))
                logger.error(f"Unexpected error during connection test: {secure_error_msg}")
                health_monitor.mark_unhealthy()
                return ConnectionResult(
                    success=False,
                    message="An unexpected error occurred while testing the connection.",
                    error_code=ErrorCode.CONNECTION_ERROR
                )

