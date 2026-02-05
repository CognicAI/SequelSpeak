"""
Tests for retry behavior in DBConnectionService.

These tests verify that the retry logic works correctly for transient
connection failures, including proper backoff timing, retry limits,
and health monitor updates.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import psycopg
from psycopg_pool import AsyncConnectionPool

from services.db_connection_service import DBConnectionService
from utils.connection_resilience import health_monitor, ConnectionState
from schemas.errors import ErrorCode

@pytest.fixture
def db_service():
    """Create a DBConnectionService instance with default dependencies."""
    return DBConnectionService()




@pytest.fixture(autouse=True)
def reset_health_monitor():
    """Reset health monitor state before each test to prevent state leakage."""
    health_monitor._state = ConnectionState.UNKNOWN
    health_monitor._consecutive_failures = 0
    yield
    # Cleanup after test
    health_monitor._state = ConnectionState.UNKNOWN
    health_monitor._consecutive_failures = 0


class TestDBConnectionServiceRetry:
    """Test retry behavior in DBConnectionService.test_connection()"""

    @pytest.mark.asyncio
    async def test_successful_recovery_after_transient_failures(self, db_service):
        """Test that connection recovers after transient failures"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Create successful mock connection
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(1,))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        # Fail twice, then succeed
        fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = [
                fail_exception,
                fail_exception,
                mock_pool
            ]
            
            result = await db_service.test_connection(db_url)
            
            # Verify successful recovery
            assert result.success is True
            assert result.message == "Connection successful!"
            assert mock_get_pool.call_count == 3
            assert mock_sleep.call_count == 2  # Two retries
            assert await health_monitor.get_state() == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_retry_limit_enforcement(self, db_service):
        """Test that retry attempts stop at max_retries"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Always fail
        fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = fail_exception
            
            result = await db_service.test_connection(db_url, max_retries=2)
            
            # Verify retry limit respected
            assert result.success is False
            assert result.error_code == ErrorCode.CONNECTION_LOST
            assert mock_get_pool.call_count == 3  # 1 initial + 2 retries
            assert mock_sleep.call_count == 2
            assert await health_monitor.get_state() == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, db_service):
        """Test that delays follow exponential backoff pattern"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection closed")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = fail_exception
            
            await db_service.test_connection(db_url, max_retries=3, initial_delay=1.0)
            
            # Verify exponential backoff: 1s, 2s, 4s
            assert mock_sleep.call_count == 3
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # First retry: 1s
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # Second retry: 2s
            assert mock_sleep.call_args_list[2][0][0] == 4.0  # Third retry: 4s

    @pytest.mark.asyncio
    async def test_health_monitor_updates_during_retries(self, db_service):
        """Test that health monitor is updated on each retry attempt"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection terminated")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            
            mock_get_pool.side_effect = fail_exception
            
            # Initial state
            assert await health_monitor.get_consecutive_failures() == 0
            
            await db_service.test_connection(db_url, max_retries=2)
            
            # After 3 failures (1 initial + 2 retries)
            assert await health_monitor.get_consecutive_failures() == 3
            assert await health_monitor.get_state() == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_health_monitor_reset_on_success(self, db_service):
        """Test that health monitor is reset when connection succeeds"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Set unhealthy state
        await health_monitor.mark_unhealthy()
        await health_monitor.mark_unhealthy()
        assert await health_monitor.get_consecutive_failures() == 2
        
        # Create successful connection
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(1,))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        with patch("services.db_connection_service.pool_manager.get_pool", return_value=mock_pool):
            result = await db_service.test_connection(db_url)
            
            assert result.success is True
            assert await health_monitor.get_consecutive_failures() == 0
            assert await health_monitor.get_state() == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_failure(self, db_service):
        """Test that authentication errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Auth failure should not trigger retry
        auth_error = psycopg.OperationalError("password authentication failed for user")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = auth_error
            
            result = await db_service.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.AUTH_FAILED
            assert mock_get_pool.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays

    @pytest.mark.asyncio
    async def test_no_retry_on_database_not_found(self, db_service):
        """Test that database not found errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/nonexistent"
        
        db_error = psycopg.OperationalError('database "nonexistent" does not exist')
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = db_error
            
            result = await db_service.test_connection(db_url)
            
            assert result.success is False
            assert result.error_code == ErrorCode.DATABASE_NOT_FOUND
            assert mock_get_pool.call_count == 1
            assert mock_sleep.call_count == 0

    @pytest.mark.asyncio
    async def test_connection_lost_error_code_after_retry_exhaustion(self, db_service):
        """Test that CONNECTION_LOST error code is returned after retries exhausted"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        connection_lost_errors = [
            "server closed the connection unexpectedly",
            "connection closed",
            "broken pipe",
            "connection reset",
        ]
        
        for error_msg in connection_lost_errors:
            # Reset state
            health_monitor._state = ConnectionState.UNKNOWN
            health_monitor._consecutive_failures = 0
            
            with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                
                mock_get_pool.side_effect = psycopg.OperationalError(error_msg)
                
                result = await db_service.test_connection(db_url, max_retries=1)
                
                assert result.success is False
                assert result.error_code == ErrorCode.CONNECTION_LOST, \
                    f"Expected CONNECTION_LOST for: {error_msg}"
                assert "connection was lost" in result.message.lower()

    @pytest.mark.asyncio
    async def test_custom_retry_parameters(self, db_service):
        """Test that custom max_retries and initial_delay are respected"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection dropped")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = fail_exception
            
            # Custom parameters: 1 retry, 0.5s initial delay
            await db_service.test_connection(db_url, max_retries=1, initial_delay=0.5)
            
            assert mock_get_pool.call_count == 2  # 1 initial + 1 retry
            assert mock_sleep.call_count == 1
            assert mock_sleep.call_args_list[0][0][0] == 0.5  # First delay: 0.5s

    @pytest.mark.asyncio
    async def test_retry_with_mixed_errors(self, db_service):
        """Test retry behavior with different error types"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # First attempt: retryable error
        # Second attempt: non-retryable error (should stop retrying)
        connection_lost = psycopg.OperationalError("server closed the connection unexpectedly")
        auth_failed = psycopg.OperationalError("password authentication failed")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = [connection_lost, auth_failed]
            
            result = await db_service.test_connection(db_url, max_retries=5)
            
            # Should retry after first error, then fail on auth error
            assert result.success is False
            assert result.error_code == ErrorCode.AUTH_FAILED
            assert mock_get_pool.call_count == 2  # Stopped after auth error
            assert mock_sleep.call_count == 1  # Only one retry

    @pytest.mark.asyncio
    async def test_no_retry_on_ssl_error(self, db_service):
        """Test that SSL errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        ssl_error = psycopg.OperationalError("SSL SYSCALL error: Connection reset by peer")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = ssl_error
            
            result = await db_service.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.HOST_UNREACHABLE  # SSL SYSCALL is network error
            assert mock_get_pool.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays

    @pytest.mark.asyncio
    async def test_no_retry_on_timeout_error(self, db_service):
        """Test that timeout errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        timeout_error = psycopg.OperationalError("timeout expired")
        
        with patch("services.db_connection_service.pool_manager.get_pool") as mock_get_pool, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            
            mock_get_pool.side_effect = timeout_error
            
            result = await db_service.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.TIMEOUT
            assert mock_get_pool.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays
