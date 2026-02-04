"""
Tests for connection resilience utilities.

Tests cover:
- Connection lost error detection
- Decorator behavior for graceful failure handling
- Health monitor state management
- Credential safety in logs and error messages
"""

import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# Add backend to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from utils.connection_resilience import (
    ConnectionState,
    is_connection_lost_error,
    detect_connection_failure,
    ConnectionHealthMonitor,
    CONNECTION_LOST_PATTERNS,
)
from schemas.errors import ErrorCode, ConnectionResult


@pytest.fixture(autouse=True)
def reset_health_monitor():
    """Reset health monitor state before each test to prevent state leakage."""
    from utils.connection_resilience import health_monitor
    health_monitor._state = ConnectionState.UNKNOWN
    health_monitor._consecutive_failures = 0
    yield
    # Cleanup after test
    health_monitor._state = ConnectionState.UNKNOWN
    health_monitor._consecutive_failures = 0


# ============================================================================
# ERROR DETECTION TESTS
# ============================================================================

class TestIsConnectionLostError:
    """Tests for the is_connection_lost_error function."""

    def test_detects_connection_closed(self):
        """Test detection of 'connection closed' error."""
        error = psycopg.OperationalError("connection closed unexpectedly")
        assert is_connection_lost_error(error) is True

    def test_detects_server_closed_connection(self):
        """Test detection of server closing connection unexpectedly."""
        error = psycopg.OperationalError("server closed the connection unexpectedly")
        assert is_connection_lost_error(error) is True

    def test_detects_connection_reset(self):
        """Test detection of connection reset error."""
        error = psycopg.OperationalError("connection reset by peer")
        assert is_connection_lost_error(error) is True

    def test_detects_broken_pipe(self):
        """Test detection of broken pipe error."""
        error = psycopg.OperationalError("broken pipe")
        assert is_connection_lost_error(error) is True

    def test_detects_connection_terminated(self):
        """Test detection of connection terminated error."""
        error = psycopg.OperationalError("connection terminated")
        assert is_connection_lost_error(error) is True

    def test_detects_interface_error_closed(self):
        """Test detection of interface error indicating closed connection."""
        error = psycopg.InterfaceError("the connection is closed")
        assert is_connection_lost_error(error) is True

    def test_detects_interface_error_invalid(self):
        """Test detection of interface error indicating invalid connection."""
        error = psycopg.InterfaceError("cursor is invalid")
        assert is_connection_lost_error(error) is True

    def test_detects_connection_error(self):
        """Test detection of generic ConnectionError."""
        error = ConnectionError("Connection refused")
        assert is_connection_lost_error(error) is True

    def test_detects_broken_pipe_error(self):
        """Test detection of BrokenPipeError."""
        error = BrokenPipeError("Broken pipe")
        assert is_connection_lost_error(error) is True

    def test_detects_connection_reset_error(self):
        """Test detection of ConnectionResetError."""
        error = ConnectionResetError("Connection reset by peer")
        assert is_connection_lost_error(error) is True


class TestIsConnectionLostErrorNegative:
    """Tests for errors that should NOT be classified as connection lost."""

    def test_auth_failure_not_connection_lost(self):
        """Test that authentication failure is NOT a connection lost error."""
        error = psycopg.OperationalError("password authentication failed for user")
        assert is_connection_lost_error(error) is False

    def test_database_not_found_not_connection_lost(self):
        """Test that database not found is NOT a connection lost error."""
        error = psycopg.OperationalError("database \"testdb\" does not exist")
        assert is_connection_lost_error(error) is False

    def test_host_unreachable_not_connection_lost(self):
        """Test that host unreachable is NOT a connection lost error."""
        error = psycopg.OperationalError("could not connect to server: Connection refused")
        assert is_connection_lost_error(error) is False

    def test_timeout_not_connection_lost(self):
        """Test that initial timeout is NOT a connection lost error."""
        error = psycopg.OperationalError("timeout expired")
        assert is_connection_lost_error(error) is False

    def test_generic_value_error_not_connection_lost(self):
        """Test that ValueError is NOT a connection lost error."""
        error = ValueError("Invalid parameter")
        assert is_connection_lost_error(error) is False

    def test_generic_exception_not_connection_lost(self):
        """Test that generic Exception is NOT a connection lost error."""
        error = Exception("Something went wrong")
        assert is_connection_lost_error(error) is False


# ============================================================================
# DECORATOR TESTS
# ============================================================================

class TestDetectConnectionFailureDecorator:
    """Tests for the detect_connection_failure decorator."""

    def test_decorator_catches_interface_error(self):
        """Test that decorator catches InterfaceError and returns ConnectionResult."""
        @detect_connection_failure
        def failing_operation():
            raise psycopg.InterfaceError("the connection is closed")

        result = failing_operation()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_LOST
        assert "connection was lost" in result.message

    def test_decorator_catches_connection_lost_operational_error(self):
        """Test that decorator catches OperationalError for connection lost."""
        @detect_connection_failure
        def failing_operation():
            raise psycopg.OperationalError("server closed the connection unexpectedly")

        result = failing_operation()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_LOST

    def test_decorator_reraises_non_connection_lost_operational_error(self):
        """Test that decorator re-raises OperationalError that is not connection lost."""
        @detect_connection_failure
        def failing_operation():
            raise psycopg.OperationalError("password authentication failed")

        # Should re-raise, not catch
        with pytest.raises(psycopg.OperationalError):
            failing_operation()

    def test_decorator_catches_broken_pipe(self):
        """Test that decorator catches BrokenPipeError."""
        @detect_connection_failure
        def failing_operation():
            raise BrokenPipeError("Broken pipe")

        result = failing_operation()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_LOST

    def test_decorator_catches_connection_reset(self):
        """Test that decorator catches ConnectionResetError."""
        @detect_connection_failure
        def failing_operation():
            raise ConnectionResetError("Connection reset by peer")

        result = failing_operation()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_LOST

    def test_decorator_catches_unexpected_error(self):
        """Test that decorator catches unexpected errors gracefully."""
        @detect_connection_failure
        def failing_operation():
            raise RuntimeError("Unexpected runtime error")

        result = failing_operation()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_ERROR
        assert "unexpected error" in result.message

    def test_decorator_passes_through_success(self):
        """Test that decorator passes through successful results."""
        @detect_connection_failure
        def successful_operation():
            return ConnectionResult(success=True, message="All good")

        result = successful_operation()
        
        assert result.success is True
        assert result.message == "All good"

    def test_decorator_no_crash_on_failure(self):
        """Test that decorator never crashes the application."""
        @detect_connection_failure
        def catastrophic_failure():
            raise Exception("Total system failure")

        # Should NOT raise, should return ConnectionResult
        result = catastrophic_failure()
        
        assert isinstance(result, ConnectionResult)
        assert result.success is False


# ============================================================================
# HEALTH MONITOR TESTS
# ============================================================================

class TestConnectionHealthMonitor:
    """Tests for the ConnectionHealthMonitor class."""

    @pytest.mark.asyncio
    async def test_initial_state_is_unknown(self):
        """Test that initial state is UNKNOWN."""
        monitor = ConnectionHealthMonitor()
        assert await monitor.get_state() == ConnectionState.UNKNOWN

    @pytest.mark.asyncio
    async def test_initial_consecutive_failures_is_zero(self):
        """Test that initial consecutive failures count is 0."""
        monitor = ConnectionHealthMonitor()
        assert await monitor.get_consecutive_failures() == 0

    @pytest.mark.asyncio
    async def test_mark_healthy_sets_connected_state(self):
        """Test that mark_healthy sets state to CONNECTED."""
        monitor = ConnectionHealthMonitor()
        await monitor.mark_healthy()
        assert await monitor.get_state() == ConnectionState.CONNECTED
        assert await monitor.is_healthy() is True

    @pytest.mark.asyncio
    async def test_mark_healthy_resets_failure_count(self):
        """Test that mark_healthy resets consecutive failures."""
        monitor = ConnectionHealthMonitor()
        await monitor.mark_unhealthy()
        await monitor.mark_unhealthy()
        assert await monitor.get_consecutive_failures() == 2
        
        await monitor.mark_healthy()
        assert await monitor.get_consecutive_failures() == 0

    @pytest.mark.asyncio
    async def test_mark_unhealthy_sets_disconnected_state(self):
        """Test that mark_unhealthy sets state to DISCONNECTED."""
        monitor = ConnectionHealthMonitor()
        await monitor.mark_unhealthy()
        assert await monitor.get_state() == ConnectionState.DISCONNECTED
        assert await monitor.is_healthy() is False

    @pytest.mark.asyncio
    async def test_mark_unhealthy_increments_failure_count(self):
        """Test that mark_unhealthy increments consecutive failures."""
        monitor = ConnectionHealthMonitor()
        await monitor.mark_unhealthy()
        assert await monitor.get_consecutive_failures() == 1
        await monitor.mark_unhealthy()
        assert await monitor.get_consecutive_failures() == 2
        await monitor.mark_unhealthy()
        assert await monitor.get_consecutive_failures() == 3

    @pytest.mark.asyncio
    async def test_check_connection_success(self):
        """Test check_connection with successful connection."""
        from unittest.mock import AsyncMock
        from psycopg_pool import AsyncConnectionPool
        
        monitor = ConnectionHealthMonitor()
        
        # Create async mocks for pool-based connection
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
        
        with patch('services.connection_pool.pool_manager.get_pool', return_value=mock_pool):
            result = await monitor.check_connection("postgres://user:pass@localhost:5432/db")
            
            assert result.success is True
            assert await monitor.get_state() == ConnectionState.CONNECTED
            assert await monitor.is_healthy() is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self):
        """Test check_connection with connection failure."""
        monitor = ConnectionHealthMonitor()
        
        with patch('services.connection_pool.pool_manager.get_pool', side_effect=psycopg.OperationalError("connection refused")):
            result = await monitor.check_connection("postgres://user:pass@localhost:5432/db")
            
            assert result.success is False
            assert await monitor.get_state() == ConnectionState.DISCONNECTED
            assert await monitor.is_healthy() is False

    @pytest.mark.asyncio
    async def test_check_connection_detects_connection_lost(self):
        """Test that check_connection detects connection lost errors."""
        monitor = ConnectionHealthMonitor()
        
        with patch('services.connection_pool.pool_manager.get_pool', side_effect=psycopg.OperationalError("server closed the connection unexpectedly")):
            result = await monitor.check_connection("postgres://user:pass@localhost:5432/db")
            
            assert result.success is False
            assert result.error_code == ErrorCode.CONNECTION_LOST
    
    @pytest.mark.asyncio
    async def test_check_connection_retries_on_transient_failure(self):
        """Test that health check retries once on transient connection failure."""
        from unittest.mock import AsyncMock
        from psycopg_pool import AsyncConnectionPool
        
        monitor = ConnectionHealthMonitor()
        
        # Create async mocks
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        
        # First call: connection lost error
        # Second call: success
        call_count = [0]
        
        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise psycopg.OperationalError("connection closed")
            # Second call succeeds
            return None
        
        mock_cursor.execute = mock_execute
        mock_cursor.fetchone = AsyncMock(return_value=(1,))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        with patch('services.connection_pool.pool_manager.get_pool', return_value=mock_pool):
            result = await monitor.check_connection("postgres://test@localhost/db")
        
        assert result.success is True
        assert result.message == "Connection is healthy"
        # Verify execute was called twice (initial + 1 retry)
        assert call_count[0] == 2
    
    @pytest.mark.asyncio
    async def test_check_connection_fails_after_max_retries(self):
        """Test that health check fails after exhausting retries."""
        from unittest.mock import AsyncMock
        from psycopg_pool import AsyncConnectionPool
        
        monitor = ConnectionHealthMonitor()
        
        # Mock to fail consistently with connection lost error
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        
        # Always fail with connection lost
        mock_cursor.execute = AsyncMock(side_effect=psycopg.OperationalError("connection closed"))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        with patch('services.connection_pool.pool_manager.get_pool', return_value=mock_pool):
            result = await monitor.check_connection("postgres://test@localhost/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_LOST
        # Verify execute was called twice (initial + 1 retry)
        assert mock_cursor.execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_check_connection_no_retry_on_non_transient_error(self):
        """Test that health check does not retry on non-transient errors."""
        from unittest.mock import AsyncMock
        from psycopg_pool import AsyncConnectionPool
        
        monitor = ConnectionHealthMonitor()
        
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        
        # SSL error (non-retryable)
        mock_cursor.execute = AsyncMock(side_effect=psycopg.OperationalError("SSL error: certificate verify failed"))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        with patch('services.connection_pool.pool_manager.get_pool', return_value=mock_pool):
            result = await monitor.check_connection("postgres://test@localhost/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_ERROR
        # Verify execute was called only once (no retry)
        assert mock_cursor.execute.call_count == 1
    
    @pytest.mark.asyncio
    async def test_check_connection_no_retry_on_auth_failure(self):
        """Test that health check does not retry on authentication failures."""
        from unittest.mock import AsyncMock
        from psycopg_pool import AsyncConnectionPool
        
        monitor = ConnectionHealthMonitor()
        
        mock_pool = AsyncMock(spec=AsyncConnectionPool)
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        
        # Auth error (non-retryable)
        mock_cursor.execute = AsyncMock(side_effect=psycopg.OperationalError("password authentication failed"))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection = MagicMock(return_value=mock_conn)
        
        with patch('services.connection_pool.pool_manager.get_pool', return_value=mock_pool):
            result = await monitor.check_connection("postgres://test@localhost/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.CONNECTION_ERROR
        # Verify execute was called only once (no retry)
        assert mock_cursor.execute.call_count == 1


# ============================================================================
# CREDENTIAL SAFETY TESTS
# ============================================================================

class TestCredentialSafety:
    """Tests to ensure credentials are never exposed in logs or error messages."""

    def test_no_credentials_in_decorator_error_message(self):
        """Test that credentials don't appear in decorator error messages."""
        @detect_connection_failure
        def failing_with_creds():
            raise psycopg.InterfaceError("connection closed for postgres://admin:secretpass@prod.db.com:5432/mydb")

        result = failing_with_creds()
        
        assert "secretpass" not in result.message
        assert "admin" not in result.message

    def test_no_url_in_error_message(self):
        """Test that full URLs don't appear in error messages."""
        @detect_connection_failure
        def failing_operation():
            raise psycopg.OperationalError("broken pipe")

        result = failing_operation()
        
        assert "postgres://" not in result.message
        assert "postgresql://" not in result.message

    @patch('utils.connection_resilience.logger')
    def test_credentials_masked_in_logs(self, mock_logger):
        """Test that credentials are masked in log messages."""
        @detect_connection_failure
        def failing_with_url():
            raise psycopg.InterfaceError("connection closed for postgres://user:secret@host/db")

        failing_with_url()
        
        # Get all log calls
        log_call_args = [str(call) for call in mock_logger.error.call_args_list]
        log_messages = " ".join(log_call_args)
        
        # Credentials should be masked: the raw secret must not appear, and masked value should.
        assert "secret" not in log_messages
        assert "***" in log_messages


# ============================================================================
# CONNECTION LOST PATTERNS TESTS
# ============================================================================

class TestConnectionLostPatterns:
    """Tests for all defined connection lost patterns."""

    @pytest.mark.parametrize("pattern", CONNECTION_LOST_PATTERNS)
    def test_all_patterns_detected(self, pattern):
        """Test that all defined patterns are detected as connection lost."""
        error = psycopg.OperationalError(f"Database error: {pattern}")
        assert is_connection_lost_error(error) is True, f"Pattern '{pattern}' was not detected"
