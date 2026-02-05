import logging
import psycopg
import re
import asyncio
from typing import Tuple, Protocol, Optional, Callable, Any
from urllib.parse import urlparse
from abc import ABC, abstractmethod
from config import settings
from schemas.errors import ErrorCode, ConnectionResult
from utils.security import mask_connection_url
from utils.input_validator import validate_connection_url, ValidationResult
from utils.connection_resilience import is_connection_lost_error, health_monitor, ConnectionHealthMonitor
from utils.circuit_breaker import db_circuit_breaker, CircuitBreakerError, CircuitBreaker
from utils.patterns import PatternMatcher, PatternCategory
from services.connection_pool import pool_manager, ConnectionPoolManager

# Configure logger
logger = logging.getLogger(__name__)


# Protocol definitions for dependency injection
class HealthMonitorProtocol(Protocol):
    """Protocol for health monitor dependencies."""
    async def mark_healthy(self) -> None: ...
    async def mark_unhealthy(self) -> None: ...


class ErrorClassifier:
    """
    Classifies database connection errors into specific error types.
    Uses a data-driven approach with centralized pattern matching.
    
    Can be injected with custom pattern matcher for testing.
    """
    
    # Error patterns mapped to (PatternCategory, ErrorCode, user_message_template)
    # Using centralized PatternCategory for consistency across the codebase
    ERROR_MAPPINGS = [
        # Authentication errors
        (
            PatternCategory.AUTH_ERROR,
            ErrorCode.AUTH_FAILED,
            "Connection failed: Authentication error. "
            "Please verify your username, password, and access permissions."
        ),
        # Database not found
        (
            PatternCategory.DATABASE_NOT_FOUND,
            ErrorCode.DATABASE_NOT_FOUND,
            "Connection failed: The specified database could not be found. "
            "Please verify the database name and that it exists on the server."
        ),
        # SSL/TLS errors
        (
            PatternCategory.SSL_ERROR,
            ErrorCode.SSL_ERROR,
            "Connection failed: SSL/TLS certificate error. "
            "Please verify your SSL configuration and certificate validity."
        ),
        # Timeout errors
        (
            PatternCategory.TIMEOUT_ERROR,
            ErrorCode.TIMEOUT,
            "Connection failed: Connection attempt timed out after {timeout} seconds. "
            "Please verify the host, port, and network connectivity, or try increasing the timeout."
        ),
        # Network/Host errors
        (
            PatternCategory.HOST_UNREACHABLE,
            ErrorCode.HOST_UNREACHABLE,
            "Connection failed: Unable to reach the database server. "
            "Please verify the host, port, and network connectivity."
        ),
    ]
    
    def __init__(self, pattern_matcher: type = PatternMatcher):
        """
        Initialize error classifier with optional custom pattern matcher.
        
        Args:
            pattern_matcher: Pattern matching class (default: PatternMatcher)
        """
        self.pattern_matcher = pattern_matcher
    
    def classify_error(self, error_details: str, timeout: int) -> Tuple[ErrorCode, str]:
        """
        Classifies a database error based on centralized pattern matching.
        
        Args:
            error_details: The error message from the database driver
            timeout: The connection timeout value for message templating
            
        Returns:
            Tuple of (ErrorCode, user_friendly_message)
        """
        # Use pattern matcher for consistent detection
        for pattern_category, error_code, message_template in self.ERROR_MAPPINGS:
            if self.pattern_matcher.matches(error_details, pattern_category):
                message = message_template.format(timeout=timeout)
                return error_code, message
        
        # Fallback generic error
        return (
            ErrorCode.CONNECTION_ERROR,
            "Connection failed: Unable to connect to the database. "
            "Please verify your host, port, database name, and credentials."
        )


class DBConnectionService:
    """
    Database connection service with dependency injection support.
    
    Supports constructor injection for testability and flexibility.
    """
    
    def __init__(
        self,
        pool_manager: Optional[ConnectionPoolManager] = None,
        health_monitor: Optional[HealthMonitorProtocol] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        error_classifier: Optional[ErrorClassifier] = None,
        url_validator: Optional[Callable[[str], ValidationResult]] = None,
        url_masker: Optional[Callable[[str], str]] = None,
        connection_lost_detector: Optional[Callable[[Exception], bool]] = None,
        connection_timeout: Optional[int] = None,
        retry_max: Optional[int] = None,
        retry_initial_delay: Optional[float] = None,
        pool_min_size: Optional[int] = None,
        pool_max_size: Optional[int] = None,
        pool_timeout: Optional[int] = None,
    ):
        """
        Initialize connection service with injected dependencies.
        
        All dependencies are optional and default to production implementations.
        This enables easy testing with mocks and environment-specific configuration.
        
        Args:
            pool_manager: Connection pool manager (default: global pool_manager)
            health_monitor: Health monitoring instance (default: global health_monitor)
            circuit_breaker: Circuit breaker instance (default: global db_circuit_breaker)
            error_classifier: Error classification instance (default: new ErrorClassifier)
            url_validator: URL validation function (default: validate_connection_url)
            url_masker: URL masking function (default: mask_connection_url)
            connection_lost_detector: Connection lost detection function (default: is_connection_lost_error)
            connection_timeout: Connection timeout in seconds (default: from settings)
            retry_max: Maximum retry attempts (default: from settings)
            retry_initial_delay: Initial retry delay in seconds (default: from settings)
            pool_min_size: Pool minimum size (default: from settings)
            pool_max_size: Pool maximum size (default: from settings)
            pool_timeout: Pool timeout in seconds (default: from settings)
        """
        # Import global defaults to avoid circular imports
        from services.connection_pool import pool_manager as default_pool_manager
        from utils.connection_resilience import health_monitor as default_health_monitor
        from utils.circuit_breaker import db_circuit_breaker as default_circuit_breaker
        
        # Inject dependencies with fallback to defaults
        self.pool_manager = pool_manager or default_pool_manager
        self.health_monitor = health_monitor or default_health_monitor
        self.circuit_breaker = circuit_breaker or default_circuit_breaker
        self.error_classifier = error_classifier or ErrorClassifier()
        self.url_validator = url_validator or validate_connection_url
        self.url_masker = url_masker or mask_connection_url
        self.connection_lost_detector = connection_lost_detector or is_connection_lost_error
        
        # Configuration with fallback to settings
        self.connection_timeout = connection_timeout if connection_timeout is not None else settings.db_connection_timeout
        self.retry_max = retry_max if retry_max is not None else settings.connection_retry_max
        self.retry_initial_delay = retry_initial_delay if retry_initial_delay is not None else settings.connection_retry_initial_delay
        self.pool_min_size = pool_min_size if pool_min_size is not None else settings.db_pool_min_size
        self.pool_max_size = pool_max_size if pool_max_size is not None else settings.db_pool_max_size
        self.pool_timeout = pool_timeout if pool_timeout is not None else settings.db_pool_timeout
    
    def parse_and_verify_url(self, url: str) -> ConnectionResult:
        """
        Parses the connection URL and validates its structure.
        Performs security validation before structural parsing.
        Returns a ConnectionResult with success status and message.
        """
        # Security validation first - check for injection patterns and dangerous chars
        security_validation = self.url_validator(url)
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

    async def test_connection_oneshot(self, url: str) -> ConnectionResult:
        """
        Test database connection using a one-shot connection (no pooling).
        Protected by circuit breaker to prevent overwhelming the database.
        
        This method creates a direct connection that is immediately closed after testing,
        ensuring credentials are not cached in memory. Suitable for user-initiated
        connection tests where each request may use different credentials.
        
        Args:
            url: Database connection URL with embedded credentials
            
        Returns:
            ConnectionResult indicating success or failure
            
        Note:
            Unlike test_connection(), this method does not use connection pooling
            and does not retry on transient failures. It's designed for interactive
            testing where immediate feedback is more important than resilience.
        """
        # Wrap the actual connection test in circuit breaker
        async def _test():
            try:
                # Create one-shot connection with timeout
                async with await psycopg.AsyncConnection.connect(
                    url,
                    connect_timeout=self.connection_timeout
                ) as conn:
                    # Test the connection with a simple query
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                        result = await cur.fetchone()
                        
                        if result == (1,):
                            logger.info("One-shot connection test successful")
                            return ConnectionResult(
                                success=True,
                                message="Connection successful!"
                            )
                        else:
                            logger.warning("Connection test query returned unexpected result")
                            return ConnectionResult(
                                success=False,
                                message="Connection verification query failed.",
                                error_code=ErrorCode.CONNECTION_ERROR
                            )
                # Connection automatically closed when exiting context manager
                
            except psycopg.OperationalError as e:
                error_details = str(e).strip()
                secure_error_details = self.url_masker(error_details)
                logger.error(f"One-shot connection test failed: {secure_error_details}")
                
                # Classify the error using the ErrorClassifier
                error_code, error_message = self.error_classifier.classify_error(
                    error_details,
                    self.connection_timeout
                )
                
                return ConnectionResult(
                    success=False,
                    message=error_message,
                    error_code=error_code
                )
                
            except Exception as e:
                secure_error_msg = self.url_masker(str(e))
                logger.error(f"Unexpected error during one-shot connection test: {secure_error_msg}")
                return ConnectionResult(
                    success=False,
                    message="An unexpected error occurred while testing the connection.",
                    error_code=ErrorCode.CONNECTION_ERROR
                )
        
        # Execute with circuit breaker protection
        try:
            return await self.circuit_breaker.call(_test)
        except CircuitBreakerError as e:
            logger.warning(f"Circuit breaker blocked connection test: {e}")
            return ConnectionResult(
                success=False,
                message=str(e),
                error_code=ErrorCode.CONNECTION_ERROR
            )

    async def test_connection(self, url: str, max_retries: int = None, initial_delay: float = None) -> ConnectionResult:
        """
        Attempts to connect to the PostgreSQL database using the provided URL with async pooling.
        Automatically retries on transient connection failures with exponential backoff.
        
        DEPRECATED: This method uses connection pooling which caches credentials in memory.
        For user-initiated connection tests, use test_connection_oneshot() instead.
        This method is retained for internal use by health checks and persistent connections.
        
        Args:
            url: Database connection URL
            max_retries: Maximum number of retry attempts
                        (default: from injected retry_max or settings.connection_retry_max)
            initial_delay: Initial delay before first retry in seconds
                          (default: from injected retry_initial_delay or settings.connection_retry_initial_delay)
        
        Returns:
            ConnectionResult indicating success or failure
        """
        # Use injected defaults if not specified
        if max_retries is None:
            max_retries = self.retry_max
        if initial_delay is None:
            initial_delay = self.retry_initial_delay
        
        retries = 0
        delay = initial_delay
        
        while retries <= max_retries:
            try:
                # Get pool inside retry loop to handle pool exhaustion scenarios
                pool = await self.pool_manager.get_pool(
                    url,
                    min_size=self.pool_min_size,
                    max_size=self.pool_max_size,
                    timeout=self.pool_timeout
                )
                
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                        result = await cur.fetchone()
                        if result == (1,):
                            await self.health_monitor.mark_healthy()
                            return ConnectionResult(success=True, message="Connection successful!")
                        else:
                            await self.health_monitor.mark_unhealthy()
                            return ConnectionResult(
                                success=False,
                                message="Connection verification query failed.",
                                error_code=ErrorCode.CONNECTION_ERROR
                            )
                        
            except psycopg.OperationalError as e:
                error_details = str(e).strip()
                secure_error_details = self.url_masker(error_details)
                logger.error(f"Database Connection Failed: {secure_error_details}")

                # Check if this is a connection lost error that should trigger retry
                if self.connection_lost_detector(e) and retries < max_retries:
                    retries += 1
                    await self.health_monitor.mark_unhealthy()
                    logger.warning(
                        f"Connection lost. Retrying in {delay:.1f}s... "
                        f"(Attempt {retries}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2.0  # Exponential backoff
                    continue  # Retry the connection

                # If we're here, either it's not retryable or we've exhausted retries
                await self.health_monitor.mark_unhealthy()
                
                # Check if this was a connection lost error (retries exhausted)
                if self.connection_lost_detector(e):
                    return ConnectionResult(
                        success=False,
                        message="Database connection was lost. Please try again.",
                        error_code=ErrorCode.CONNECTION_LOST
                    )

                # Classify the error using the ErrorClassifier
                error_code, error_message = self.error_classifier.classify_error(
                    error_details, 
                    self.connection_timeout
                )
                
                return ConnectionResult(
                    success=False,
                    message=error_message,
                    error_code=error_code
                )

            except Exception as e:
                secure_error_msg = self.url_masker(str(e))
                logger.error(f"Unexpected error during connection test: {secure_error_msg}")
                await self.health_monitor.mark_unhealthy()
                return ConnectionResult(
                    success=False,
                    message="An unexpected error occurred while testing the connection.",
                    error_code=ErrorCode.CONNECTION_ERROR
                )


