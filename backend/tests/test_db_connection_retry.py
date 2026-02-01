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
from unittest.mock import MagicMock, patch
import psycopg
import time

from services.db_connection_service import DBConnectionService
from utils.connection_resilience import health_monitor, ConnectionState
from schemas.errors import ErrorCode


class TestDBConnectionServiceRetry:
    """Test retry behavior in DBConnectionService.test_connection()"""

    def setup_method(self):
        """Reset health monitor before each test"""
        # Reset to initial state
        health_monitor._state = ConnectionState.UNKNOWN
        health_monitor._consecutive_failures = 0

    def test_successful_recovery_after_transient_failures(self):
        """Test that connection recovers after transient failures"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Create successful mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)
        
        # Fail twice, then succeed
        fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = [
                fail_exception,
                fail_exception,
                MagicMock(__enter__=MagicMock(return_value=mock_conn), __exit__=MagicMock())
            ]
            
            result = DBConnectionService.test_connection(db_url)
            
            # Verify successful recovery
            assert result.success is True
            assert result.message == "Connection successful!"
            assert mock_connect.call_count == 3
            assert mock_sleep.call_count == 2  # Two retries
            assert health_monitor.state == ConnectionState.CONNECTED

    def test_retry_limit_enforcement(self):
        """Test that retry attempts stop at max_retries"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Always fail
        fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = fail_exception
            
            result = DBConnectionService.test_connection(db_url, max_retries=2)
            
            # Verify retry limit respected
            assert result.success is False
            assert result.error_code == ErrorCode.CONNECTION_LOST
            assert mock_connect.call_count == 3  # 1 initial + 2 retries
            assert mock_sleep.call_count == 2
            assert health_monitor.state == ConnectionState.DISCONNECTED

    def test_exponential_backoff_timing(self):
        """Test that delays follow exponential backoff pattern"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection closed")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = fail_exception
            
            DBConnectionService.test_connection(db_url, max_retries=3, initial_delay=1.0)
            
            # Verify exponential backoff: 1s, 2s, 4s
            assert mock_sleep.call_count == 3
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # First retry: 1s
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # Second retry: 2s
            assert mock_sleep.call_args_list[2][0][0] == 4.0  # Third retry: 4s

    def test_health_monitor_updates_during_retries(self):
        """Test that health monitor is updated on each retry attempt"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection terminated")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep"):
            
            mock_connect.side_effect = fail_exception
            
            # Initial state
            assert health_monitor.consecutive_failures == 0
            
            DBConnectionService.test_connection(db_url, max_retries=2)
            
            # After 3 failures (1 initial + 2 retries)
            assert health_monitor.consecutive_failures == 3
            assert health_monitor.state == ConnectionState.DISCONNECTED

    def test_health_monitor_reset_on_success(self):
        """Test that health monitor is reset when connection succeeds"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Set unhealthy state
        health_monitor.mark_unhealthy()
        health_monitor.mark_unhealthy()
        assert health_monitor.consecutive_failures == 2
        
        # Create successful connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)
        
        with patch("psycopg.connect") as mock_connect:
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_connect.return_value.__exit__.return_value = None
            
            result = DBConnectionService.test_connection(db_url)
            
            assert result.success is True
            assert health_monitor.consecutive_failures == 0
            assert health_monitor.state == ConnectionState.CONNECTED

    def test_no_retry_on_auth_failure(self):
        """Test that authentication errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # Auth failure should not trigger retry
        auth_error = psycopg.OperationalError("password authentication failed for user")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = auth_error
            
            result = DBConnectionService.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.AUTH_FAILED
            assert mock_connect.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays

    def test_no_retry_on_database_not_found(self):
        """Test that database not found errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/nonexistent"
        
        db_error = psycopg.OperationalError('database "nonexistent" does not exist')
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = db_error
            
            result = DBConnectionService.test_connection(db_url)
            
            assert result.success is False
            assert result.error_code == ErrorCode.DATABASE_NOT_FOUND
            assert mock_connect.call_count == 1
            assert mock_sleep.call_count == 0

    def test_connection_lost_error_code_after_retry_exhaustion(self):
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
            
            with patch("psycopg.connect") as mock_connect, \
                 patch("time.sleep"):
                
                mock_connect.side_effect = psycopg.OperationalError(error_msg)
                
                result = DBConnectionService.test_connection(db_url, max_retries=1)
                
                assert result.success is False
                assert result.error_code == ErrorCode.CONNECTION_LOST, \
                    f"Expected CONNECTION_LOST for: {error_msg}"
                assert "connection was lost" in result.message.lower()

    def test_custom_retry_parameters(self):
        """Test that custom max_retries and initial_delay are respected"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        fail_exception = psycopg.OperationalError("connection dropped")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = fail_exception
            
            # Custom parameters: 1 retry, 0.5s initial delay
            DBConnectionService.test_connection(db_url, max_retries=1, initial_delay=0.5)
            
            assert mock_connect.call_count == 2  # 1 initial + 1 retry
            assert mock_sleep.call_count == 1
            assert mock_sleep.call_args_list[0][0][0] == 0.5  # First delay: 0.5s

    def test_retry_with_mixed_errors(self):
        """Test retry behavior with different error types"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        # First attempt: retryable error
        # Second attempt: non-retryable error (should stop retrying)
        connection_lost = psycopg.OperationalError("server closed the connection unexpectedly")
        auth_failed = psycopg.OperationalError("password authentication failed")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = [connection_lost, auth_failed]
            
            result = DBConnectionService.test_connection(db_url, max_retries=5)
            
            # Should retry after first error, then fail on auth error
            assert result.success is False
            assert result.error_code == ErrorCode.AUTH_FAILED
            assert mock_connect.call_count == 2  # Stopped after auth error
            assert mock_sleep.call_count == 1  # Only one retry

    def test_no_retry_on_ssl_error(self):
        """Test that SSL errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        ssl_error = psycopg.OperationalError("SSL SYSCALL error: Connection reset by peer")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = ssl_error
            
            result = DBConnectionService.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.HOST_UNREACHABLE  # SSL SYSCALL is network error
            assert mock_connect.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays

    def test_no_retry_on_timeout_error(self):
        """Test that timeout errors are not retried"""
        db_url = "postgres://user:pass@localhost:5432/db"
        
        timeout_error = psycopg.OperationalError("timeout expired")
        
        with patch("psycopg.connect") as mock_connect, \
             patch("time.sleep") as mock_sleep:
            
            mock_connect.side_effect = timeout_error
            
            result = DBConnectionService.test_connection(db_url)
            
            # Should fail immediately without retry
            assert result.success is False
            assert result.error_code == ErrorCode.TIMEOUT
            assert mock_connect.call_count == 1  # No retries
            assert mock_sleep.call_count == 0  # No delays
