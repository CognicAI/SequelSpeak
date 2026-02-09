"""
Tests for one-shot connection method (test_connection_oneshot).

Verifies that:
- One-shot connections don't use connection pooling
- Credentials are not cached in memory
- Connections are immediately closed after testing
- Error handling works correctly without retry logic
- Multiple test requests don't create cached pools
"""

import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
import psycopg

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path to import services

from services.db_connection_service import DBConnectionService
from schemas.errors import ErrorCode

@pytest.fixture
def db_service():
    """Create a DBConnectionService instance with default dependencies."""
    return DBConnectionService()




# ============================================================================
# SUCCESSFUL CONNECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_connection_success(db_service):
    """Test successful one-shot connection without pooling"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    # Mock AsyncConnection.connect to return our mock connection
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is True
        assert result.message == "Connection successful!"
        assert result.error_code is None
        
        # Verify connection was closed (context manager __aexit__ called)
        mock_conn.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_oneshot_connection_no_pool_manager_called(db_service):
    """Verify that pool_manager.get_pool is NEVER called for one-shot connections"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn):
        with patch('services.db_connection_service.pool_manager.get_pool',
                   new_callable=AsyncMock) as mock_get_pool:
            
            result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
            
            assert result.success is True
            # Critical assertion: pool_manager should never be called
            mock_get_pool.assert_not_called()


@pytest.mark.asyncio
async def test_oneshot_multiple_connections_no_caching(db_service):
    """Verify that multiple one-shot connections don't create cached pools"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn) as mock_connect:
        
        # Test 3 different database connections
        urls = [
            "postgres://user1:pass1@host1:5432/db1",
            "postgres://user2:pass2@host2:5432/db2",
            "postgres://user3:pass3@host3:5432/db3",
        ]
        
        for url in urls:
            result = await db_service.test_connection_oneshot(url)
            assert result.success is True
        
        # Verify AsyncConnection.connect was called 3 times (once per test)
        assert mock_connect.call_count == 3
        
        # Verify each connection was closed (context manager exited)
        assert mock_conn.__aexit__.call_count == 3


@pytest.mark.asyncio
async def test_oneshot_connection_select_verification(db_service):
    """Test that SELECT 1 is executed and verified in one-shot connection"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")
        mock_cursor.fetchone.assert_called_once()


@pytest.mark.asyncio
async def test_oneshot_connection_timeout_parameter(db_service):
    """Verify that db_connection_timeout is passed to AsyncConnection.connect"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn) as mock_connect:
        
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is True
        
        # Verify connect was called with correct timeout
        mock_connect.assert_called_once()
        call_args = mock_connect.call_args
        assert call_args[0][0] == "postgres://user:pass@localhost:5432/db"
        assert 'connect_timeout' in call_args[1]


# ============================================================================
# AUTHENTICATION FAILURE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_auth_failed(db_service):
    """Test authentication failure handling in one-shot connection"""
    error = psycopg.OperationalError("password authentication failed for user \"testuser\"")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://testuser:wrongpass@localhost:5432/db")
        
        assert result.success is False
        assert "Authentication error" in result.message
        assert result.error_code == ErrorCode.AUTH_FAILED


@pytest.mark.asyncio
async def test_oneshot_no_pg_hba_entry(db_service):
    """Test no pg_hba.conf entry error in one-shot connection"""
    error = psycopg.OperationalError('no pg_hba.conf entry for host "192.168.1.100", user "testuser"')
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://testuser:pass@192.168.1.100:5432/db")
        
        assert result.success is False
        assert "Authentication error" in result.message
        assert result.error_code == ErrorCode.AUTH_FAILED


# ============================================================================
# DATABASE NOT FOUND TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_database_not_found(db_service):
    """Test database not found error in one-shot connection"""
    error = psycopg.OperationalError('database "nonexistent_db" does not exist')
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/nonexistent_db")
        
        assert result.success is False
        assert "database could not be found" in result.message
        assert result.error_code == ErrorCode.DATABASE_NOT_FOUND


# ============================================================================
# HOST UNREACHABLE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_host_unreachable(db_service):
    """Test host unreachable error in one-shot connection"""
    error = psycopg.OperationalError("could not connect to server: Connection refused")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@unreachable:5432/db")
        
        assert result.success is False
        assert "Unable to reach the database server" in result.message
        assert result.error_code == ErrorCode.HOST_UNREACHABLE


@pytest.mark.asyncio
async def test_oneshot_connection_refused(db_service):
    """Test connection refused error in one-shot connection"""
    error = psycopg.OperationalError("Connection refused (tcp://localhost:5433)")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5433/db")
        
        assert result.success is False
        assert "Unable to reach the database server" in result.message
        assert result.error_code == ErrorCode.HOST_UNREACHABLE


# ============================================================================
# SSL/TLS ERROR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_ssl_error(db_service):
    """Test SSL/TLS error in one-shot connection"""
    error = psycopg.OperationalError("SSL error: certificate verify failed")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db?sslmode=require")
        
        assert result.success is False
        assert "SSL/TLS certificate error" in result.message
        assert result.error_code == ErrorCode.SSL_ERROR


@pytest.mark.asyncio
async def test_oneshot_ssl_required(db_service):
    """Test SSL required but not supported error in one-shot connection"""
    error = psycopg.OperationalError("SSL connection has been requested but SSL is not supported")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db?sslmode=require")
        
        assert result.success is False
        assert "SSL/TLS certificate error" in result.message
        assert result.error_code == ErrorCode.SSL_ERROR


# ============================================================================
# TIMEOUT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_timeout(db_service):
    """Test connection timeout error in one-shot connection"""
    error = psycopg.OperationalError("timeout expired")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@slow-host:5432/db")
        
        assert result.success is False
        assert "timed out" in result.message
        assert result.error_code == ErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_oneshot_connection_timeout(db_service):
    """Test connection timeout alternative message in one-shot connection"""
    error = psycopg.OperationalError("connection timeout")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@slow-host:5432/db")
        
        assert result.success is False
        assert "timed out" in result.message
        assert result.error_code == ErrorCode.TIMEOUT


# ============================================================================
# ERROR SANITIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_error_no_credentials_leak(db_service):
    """Verify that error messages don't leak credentials in one-shot connection"""
    # Create error with credentials in message
    error = psycopg.OperationalError(
        "connection failed for postgres://testuser:SecretPass123@badhost:5432/db"
    )
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot(
            "postgres://testuser:SecretPass123@badhost:5432/db"
        )
        
        assert result.success is False
        # Verify password is NOT in the error message
        assert "SecretPass123" not in result.message
        # Verify a generic user-friendly message is returned
        assert "Unable to reach the database server" in result.message or "Unable to connect" in result.message


# ============================================================================
# GENERIC ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_generic_exception(db_service):
    """Test generic exception handling in one-shot connection"""
    error = Exception("Unexpected database error")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert "unexpected error" in result.message.lower()
        assert result.error_code == ErrorCode.CONNECTION_ERROR


@pytest.mark.asyncio
async def test_oneshot_query_verification_failure(db_service):
    """Test when SELECT 1 returns unexpected result in one-shot connection"""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(2,))  # Unexpected result
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn):
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert "verification" in result.message.lower()
        assert result.error_code == ErrorCode.CONNECTION_ERROR


# ============================================================================
# NO RETRY BEHAVIOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_no_retry_on_transient_failure(db_service):
    """Verify that one-shot connections do NOT retry on transient failures"""
    # Simulate a transient connection error that would trigger retry in test_connection()
    error = psycopg.OperationalError("server closed the connection unexpectedly")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error) as mock_connect:
        
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        # Critical: Should only attempt connection ONCE (no retry)
        assert mock_connect.call_count == 1


@pytest.mark.asyncio
async def test_oneshot_no_retry_on_auth_failure(db_service):
    """Verify that one-shot connections do NOT retry on auth failures"""
    error = psycopg.OperationalError("password authentication failed")
    
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               side_effect=error) as mock_connect:
        
        result = await db_service.test_connection_oneshot("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.AUTH_FAILED
        # Should only attempt connection once (no retry for non-retryable errors)
        assert mock_connect.call_count == 1


# ============================================================================
# COMPARISON WITH POOLED CONNECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_oneshot_vs_pooled_behavior(db_service):
    """
    Compare one-shot vs pooled connection behavior side-by-side.
    This test documents the key architectural differences.
    """
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    # Mock for pooled connection
    from psycopg_pool import AsyncConnectionPool
    mock_pool = AsyncMock(spec=AsyncConnectionPool)
    mock_pool.connection = MagicMock(return_value=mock_conn)
    
    url = "postgres://user:pass@localhost:5432/db"
    
    # Test one-shot connection
    with patch('psycopg.AsyncConnection.connect',
               new_callable=AsyncMock,
               return_value=mock_conn) as mock_oneshot:
        with patch('services.db_connection_service.pool_manager.get_pool',
                   new_callable=AsyncMock) as mock_pool_manager:
            
            # Call one-shot
            oneshot_result = await db_service.test_connection_oneshot(url)
            
            # Assertions for one-shot
            assert oneshot_result.success is True
            mock_oneshot.assert_called_once()  # Direct connection created
            mock_pool_manager.assert_not_called()  # Pool manager NOT used
            
    # Test pooled connection
    with patch('services.db_connection_service.pool_manager.get_pool',
               new_callable=AsyncMock,
               return_value=mock_pool) as mock_pool_manager:
        with patch('psycopg.AsyncConnection.connect',
                   new_callable=AsyncMock) as mock_direct:
            
            # Call pooled
            pooled_result = await db_service.test_connection(url)
            
            # Assertions for pooled
            assert pooled_result.success is True
            mock_pool_manager.assert_called_once()  # Pool manager used
            mock_direct.assert_not_called()  # Direct connection NOT created
