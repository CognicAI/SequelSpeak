"""
Circuit Breaker Pattern Implementation for Database Connections

Prevents cascade failures by temporarily blocking requests when the database
is consistently failing. Protects both the application and database server
from being overwhelmed during outages.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from config import settings

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Circuit tripped, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and blocks a request."""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting database operations.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests blocked immediately
    - HALF_OPEN: Testing recovery, limited requests allowed
    
    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit
        timeout: Seconds to wait before attempting recovery (OPEN -> HALF_OPEN)
        state: Current circuit state
        failure_count: Consecutive failures since last success
        last_failure_time: Unix timestamp of last failure
    """
    
    def __init__(
        self,
        failure_threshold: int = None,
        timeout: int = None,
        name: str = "database"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
                              (default: from settings.circuit_breaker_failure_threshold)
            timeout: Seconds to wait before trying again
                    (default: from settings.circuit_breaker_timeout)
            name: Name for logging purposes
        """
        self.failure_threshold = failure_threshold or settings.circuit_breaker_failure_threshold
        self.timeout = timeout or settings.circuit_breaker_timeout
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"threshold={self.failure_threshold}, timeout={self.timeout}s"
        )
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: The function to execute
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result from the function
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception from the wrapped function
        """
        # Check if circuit breaker is enabled
        if not settings.circuit_breaker_enabled:
            # Circuit breaker disabled, pass through
            return await func(*args, **kwargs)
        
        async with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"Circuit breaker '{self.name}': Attempting reset (OPEN -> HALF_OPEN)")
                    self.state = CircuitState.HALF_OPEN
                else:
                    # Circuit still open, block request
                    time_remaining = int(self.timeout - (time.time() - self.last_failure_time))
                    raise CircuitBreakerError(
                        f"Circuit breaker is open for {self.name}. "
                        f"Too many consecutive failures. "
                        f"Please try again in {time_remaining} seconds."
                    )
        
        # Execute the function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.timeout
    
    async def _on_success(self):
        """Handle successful request."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit breaker '{self.name}': Service recovered (HALF_OPEN -> CLOSED)")
                self.state = CircuitState.CLOSED
            
            # Reset failure count on success
            self.failure_count = 0
            self.last_failure_time = None
    
    async def _on_failure(self):
        """Handle failed request."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery attempt, reopen circuit
                logger.warning(
                    f"Circuit breaker '{self.name}': Recovery failed, reopening circuit (HALF_OPEN -> OPEN)"
                )
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                # Exceeded threshold, open circuit
                logger.error(
                    f"Circuit breaker '{self.name}': Opening circuit after {self.failure_count} failures"
                )
                self.state = CircuitState.OPEN
    
    async def get_state(self) -> CircuitState:
        """Get current circuit state."""
        async with self._lock:
            return self.state
    
    async def get_failure_count(self) -> int:
        """Get current failure count."""
        async with self._lock:
            return self.failure_count
    
    async def reset(self):
        """Manually reset the circuit breaker."""
        async with self._lock:
            logger.info(f"Circuit breaker '{self.name}': Manual reset")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
    
    async def force_open(self):
        """Manually open the circuit breaker."""
        async with self._lock:
            logger.warning(f"Circuit breaker '{self.name}': Manually opened")
            self.state = CircuitState.OPEN
            self.last_failure_time = time.time()


# Global circuit breaker instance for database connections
db_circuit_breaker = CircuitBreaker(name="database_connection")
