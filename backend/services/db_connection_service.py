import logging
import psycopg
import re
import time
from urllib.parse import urlparse, quote_plus, urlunparse
from config import settings
from schemas.errors import ErrorCode, ConnectionResult
from utils.security import mask_connection_url
from utils.input_validator import validate_connection_url
from utils.connection_resilience import is_connection_lost_error, health_monitor

# Configure logger
logger = logging.getLogger(__name__)

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
    def test_connection(url: str, max_retries: int = 2, initial_delay: float = 1.0) -> ConnectionResult:
        """
        Attempts to connect to the PostgreSQL database using the provided URL.
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
                with psycopg.connect(url, connect_timeout=settings.db_connection_timeout) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        result = cur.fetchone()
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
                    time.sleep(delay)
                    delay *= 2.0  # Exponential backoff
                    continue  # Retry the connection

                # If we're here, either it's not retryable or we've exhausted retries
                health_monitor.mark_unhealthy()
                details_lower = error_details.lower()
                
                # Check if this was a connection lost error (retries exhausted)
                if is_connection_lost_error(e):
                    return ConnectionResult(
                        success=False,
                        message="Database connection was lost. Please try again.",
                        error_code=ErrorCode.CONNECTION_LOST
                    )

                # Authentication / authorization issues
                if (
                    "password authentication failed" in details_lower
                    or "authentication failed" in details_lower
                    or "no pg_hba.conf entry" in details_lower
                    or "permission denied" in details_lower
                ):
                    return ConnectionResult(
                        success=False,
                        message=(
                            "Connection failed: Authentication error. "
                            "Please verify your username, password, and access permissions."
                        ),
                        error_code=ErrorCode.AUTH_FAILED
                    )

                # Database name / database not found issues
                elif "does not exist" in details_lower and "database" in details_lower:
                    return ConnectionResult(
                        success=False,
                        message=(
                            "Connection failed: The specified database could not be found. "
                            "Please verify the database name and that it exists on the server."
                        ),
                        error_code=ErrorCode.DATABASE_NOT_FOUND
                    )

                # SSL/TLS certificate issues
                elif (
                    "ssl error" in details_lower
                    or "ssl connection" in details_lower
                    or "ssl handshake" in details_lower
                    or "certificate verify" in details_lower
                    or "certificate validation" in details_lower
                    or "certificate_verify_failed" in details_lower
                    or "tlsv1" in details_lower
                    or "ssl_error" in details_lower
                    or "certificate expired" in details_lower
                    or "certificate invalid" in details_lower
                    or "self-signed certificate" in details_lower
                ):
                    return ConnectionResult(
                        success=False,
                        message=(
                            "Connection failed: SSL/TLS certificate error. "
                            "Please verify your SSL configuration and certificate validity."
                        ),
                        error_code=ErrorCode.SSL_ERROR
                    )

                # Timeout issues (check before general network errors)
                elif (
                    "timeout expired" in details_lower
                    or "timed out" in details_lower
                    or "connection timeout" in details_lower
                ):
                    return ConnectionResult(
                        success=False,
                        message=(
                            f"Connection failed: Connection attempt timed out after {settings.db_connection_timeout} seconds. "
                            "Please verify the host, port, and network connectivity, or try increasing the timeout."
                        ),
                        error_code=ErrorCode.TIMEOUT
                    )

                # Network / connectivity / host/port issues
                # Note: "SSL SYSCALL" errors are network errors during SSL handshake, not config issues
                elif (
                    "ssl syscall" in details_lower
                    or "could not connect to server" in details_lower
                    or "connection refused" in details_lower
                    or "could not translate host name" in details_lower
                    or "network is unreachable" in details_lower
                ):
                    return ConnectionResult(
                        success=False,
                        message=(
                            "Connection failed: Unable to reach the database server. "
                            "Please verify the host, port, and network connectivity."
                        ),
                        error_code=ErrorCode.HOST_UNREACHABLE
                    )

                # Fallback generic message
                else:
                    return ConnectionResult(
                        success=False,
                        message=(
                            "Connection failed: Unable to connect to the database. "
                            "Please verify your host, port, database name, and credentials."
                        ),
                        error_code=ErrorCode.CONNECTION_ERROR
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

