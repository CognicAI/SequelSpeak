"""
Comprehensive tests for DBConnectionService with async connection pooling.

Tests cover:
- Successful connection scenarios
- Authentication failures
- Database not found errors
- Host unreachable scenarios
- Connection refused errors
- SSL/TLS errors
- Timeout scenarios
- Error sanitization and credential leak prevention
- Generic error handling
- URL validation
- Error code verification
- Connection pool integration
"""

import sys
import os
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import psycopg
from psycopg_pool import AsyncConnectionPool

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path to import services

from services.db_connection_service import DBConnectionService
from schemas.errors import ErrorCode
from utils.connection_resilience import health_monitor, ConnectionState


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


# ============================================================================
# SUCCESSFUL CONNECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_success(db_service):
    """Test successful database connection via pool"""
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
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new_callable=AsyncMock,
               return_value=mock_pool):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is True
        assert result.message == "Connection successful!"
        assert result.error_code is None


@pytest.mark.asyncio
async def test_connection_success_select_verification(db_service):
    """Test that SELECT 1 is actually executed and verified"""
    mock_pool = AsyncMock(spec=AsyncConnectionPool)
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_pool.connection = MagicMock(return_value=mock_conn)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new_callable=AsyncMock,
               return_value=mock_pool):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")
        mock_cursor.fetchone.assert_called_once()


# ============================================================================
# AUTHENTICATION FAILURE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_auth_failed(db_service):
    """Test authentication failure error handling"""
    error_msg = "password authentication failed for user 'testuser'"
    
    async def raise_auth_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_auth_error)):
        result = await db_service.test_connection("postgres://user:wrongpass@localhost:5432/db")
        
        assert result.success is False
        assert "Authentication error" in result.message or "Authentication failed" in result.message
        assert "credentials" in result.message.lower() or "password" in result.message.lower()
        assert "wrongpass" not in result.message
        assert result.error_code == ErrorCode.AUTH_FAILED


@pytest.mark.asyncio
async def test_connection_auth_failed_md5(db_service):
    """Test MD5 authentication failure"""
    error_msg = "FATAL:  password authentication failed for user 'admin'"
    
    async def raise_auth_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_auth_error)):
        result = await db_service.test_connection("postgres://admin:pass@localhost:5432/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.AUTH_FAILED


# ============================================================================
# DATABASE NOT FOUND TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_database_not_found(db_service):
    """Test database does not exist error"""
    error_msg = 'database "nonexistent_db" does not exist'
    
    async def raise_db_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_db_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/nonexistent_db")
        
        assert result.success is False
        assert "database" in result.message.lower() and ("not" in result.message.lower() or "could not be found" in result.message.lower())
        assert result.error_code == ErrorCode.DATABASE_NOT_FOUND


@pytest.mark.asyncio
async def test_connection_database_not_found_alternative_message(db_service):
    """Test alternative database not found message"""
    error_msg = 'FATAL:  database "test_db" does not exist'
    
    async def raise_db_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_db_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/test_db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.DATABASE_NOT_FOUND


# ============================================================================
# HOST UNREACHABLE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_host_unreachable(db_service):
    """Test host unreachable error (connection refused)"""
    error_msg = "Connection refused: could not connect to server"
    
    async def raise_host_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_host_error)):
        result = await db_service.test_connection("postgres://user:pass@unreachable-host:5432/db")
        
        assert result.success is False
        assert "unable to reach" in result.message.lower() or "refused" in result.message.lower() or "unreachable" in result.message.lower()
        assert result.error_code == ErrorCode.HOST_UNREACHABLE


@pytest.mark.asyncio
async def test_connection_refused_port(db_service):
    """Test connection refused on specific port"""
    error_msg = "could not connect to server: Connection refused on port 5433"
    
    async def raise_host_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_host_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5433/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.HOST_UNREACHABLE


@pytest.mark.asyncio
async def test_connection_no_route_to_host(db_service):
    """Test no route to host error"""
    error_msg = "No route to host"
    
    async def raise_route_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_route_error)):
        result = await db_service.test_connection("postgres://user:pass@192.168.99.99:5432/db")
        
        assert result.success is False
        # This generic message maps to CONNECTION_ERROR, not HOST_UNREACHABLE
        assert result.error_code == ErrorCode.CONNECTION_ERROR


# ============================================================================
# SSL/TLS ERROR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_ssl_error(db_service):
    """Test SSL certificate verification failure"""
    error_msg = "SSL certificate verify failed"
    
    async def raise_ssl_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_ssl_error)):
        result = await db_service.test_connection("postgres://user:pass@secure-db.com:5432/db")
        
        assert result.success is False
        assert "SSL" in result.message or "certificate" in result.message.lower()
        assert result.error_code == ErrorCode.SSL_ERROR


@pytest.mark.asyncio
async def test_connection_ssl_required(db_service):
    """Test SSL required but not provided"""
    error_msg = "SSL connection required but not configured"
    
    async def raise_ssl_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_ssl_error)):
        result = await db_service.test_connection("postgres://user:pass@secure-db.com:5432/db")
        
        assert result.success is False
        assert result.error_code == ErrorCode.SSL_ERROR


# ============================================================================
# TIMEOUT ERROR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_timeout(db_service):
    """Test connection timeout error"""
    error_msg = "timeout expired: connection timeout after 10 seconds"
    
    async def raise_timeout_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_timeout_error)):
        result = await db_service.test_connection("postgres://user:pass@slow-server.com:5432/db")
        
        assert result.success is False
        assert "timed out" in result.message or "timeout" in result.message.lower()
        assert result.error_code == ErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_connection_timeout_timed_out(db_service):
    """Test alternative timeout error message"""
    error_msg = "server closed the connection unexpectedly: timeout timed out"
    
    async def raise_timeout_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_timeout_error)):
        result = await db_service.test_connection("postgres://user:pass@slow-server.com:5432/db")
        
        assert result.success is False
        assert "timed out" in result.message or "timeout" in result.message.lower()
        assert result.error_code == ErrorCode.TIMEOUT


# ============================================================================
# ERROR SANITIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_operational_error_sanitization(db_service):
    """Test that sensitive information is sanitized from error messages"""
    error_msg = "Sensitive internal DB info: password mismatch for user 'admin'"
    
    async def raise_sanitize_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_sanitize_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        # Error message should be sanitized
        assert "Sensitive internal DB info" not in result.message
        assert "Unable to connect" in result.message or "Connection failed" in result.message
        assert result.error_code == ErrorCode.CONNECTION_ERROR


@pytest.mark.asyncio
async def test_connection_error_no_credentials_leak(db_service):
    """Test that connection URLs with credentials never appear in error messages"""
    sensitive_url = "postgres://admin:supersecret123@prod-db.example.com:5432/production"
    
    async def raise_connection_error(*args, **kwargs):
        raise psycopg.OperationalError("Connection failed")
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_connection_error)):
        result = await db_service.test_connection(sensitive_url)
        
        assert result.success is False
        # Verify NO part of the URL appears in the message
        assert "supersecret123" not in result.message
        assert "admin" not in result.message
        assert "prod-db.example.com" not in result.message
        assert sensitive_url not in result.message


# ============================================================================
# RETRY LOGIC TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_retry_on_transient_failure(db_service):
    """Test that transient failures trigger retry with exponential backoff"""
    error_msg = "connection lost: server closed the connection unexpectedly"
    
    async def raise_transient_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_transient_error)), \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        
        result = await db_service.test_connection("postgres://user:pass@flaky-db:5432/db", max_retries=2)
        
        assert result.success is False
        # Should have retried 2 times (max_retries=2 means 3 total attempts: initial + 2 retries)
        assert mock_sleep.call_count == 2
        # Verify exponential backoff: first delay=1.0, second delay=2.0
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0


@pytest.mark.asyncio
async def test_connection_no_retry_on_auth_failure(db_service):
    """Test that authentication failures don't trigger retries"""
    error_msg = "password authentication failed"
    
    async def raise_auth_error(*args, **kwargs):
        raise psycopg.OperationalError(error_msg)
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_auth_error)), \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        
        result = await db_service.test_connection("postgres://user:wrongpass@localhost:5432/db", max_retries=2)
        
        assert result.success is False
        assert result.error_code == ErrorCode.AUTH_FAILED
        # No retries should occur for auth failures
        mock_sleep.assert_not_called()


# ============================================================================
# GENERIC ERROR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_generic_error(db_service):
    """Test generic unexpected error handling"""
    async def raise_generic_error(*args, **kwargs):
        raise Exception("Total failure")
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_generic_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert "unexpected error" in result.message.lower()
        assert result.error_code == ErrorCode.CONNECTION_ERROR


@pytest.mark.asyncio
async def test_connection_value_error(db_service):
    """Test ValueError handling"""
    async def raise_value_error(*args, **kwargs):
        raise ValueError("Invalid connection parameter")
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_value_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert "unexpected error" in result.message.lower()
        assert result.error_code == ErrorCode.CONNECTION_ERROR


@pytest.mark.asyncio
async def test_connection_type_error(db_service):
    """Test TypeError handling"""
    async def raise_type_error(*args, **kwargs):
        raise TypeError("Type mismatch")
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new=AsyncMock(side_effect=raise_type_error)):
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result.success is False
        assert "unexpected error" in result.message.lower()
        assert result.error_code == ErrorCode.CONNECTION_ERROR


# ============================================================================
# URL VALIDATION TESTS (Sync - no pool involved)
# ============================================================================

def test_parse_and_verify_url_valid(db_service):
    """Test valid URL parsing"""
    result = db_service.parse_and_verify_url("postgresql://user:pass@localhost:5432/db")
    assert result.success is True
    assert result.error_code is None


def test_parse_and_verify_url_invalid_scheme(db_service):
    """Test invalid URL scheme"""
    result = db_service.parse_and_verify_url("mysql://user:pass@localhost:3306/db")
    assert result.success is False
    assert result.error_code == ErrorCode.INVALID_URL
    assert "scheme" in result.message.lower()


def test_parse_and_verify_url_missing_host(db_service):
    """Test URL missing host"""
    result = db_service.parse_and_verify_url("postgresql:///db")
    assert result.success is False
    assert result.error_code == ErrorCode.INVALID_URL
    assert "Host is missing" in result.message


# ============================================================================
# ERROR CODE VERIFICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_error_codes_are_correct_enum_values(db_service):
    """Test that all returned error codes are valid ErrorCode enum values"""
    test_cases = [
        ("password authentication failed", ErrorCode.AUTH_FAILED),
        ('database "test" does not exist', ErrorCode.DATABASE_NOT_FOUND),
        ("connection refused", ErrorCode.HOST_UNREACHABLE),
        ("timeout expired", ErrorCode.TIMEOUT),
        ("SSL certificate verify failed", ErrorCode.SSL_ERROR),
        ("some random unknown error", ErrorCode.CONNECTION_ERROR),
    ]
    
    for error_msg, expected_code in test_cases:
        async def raise_test_error(*args, **kwargs):
            raise psycopg.OperationalError(error_msg)
        
        with patch('services.db_connection_service.pool_manager.get_pool',
                   new=AsyncMock(side_effect=raise_test_error)):
            result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
            assert result.error_code == expected_code, f"Expected {expected_code} for error: {error_msg}"


# ============================================================================
# CONNECTION POOL INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_connection_pool_is_used(db_service):
    """Test that connection pool is properly created and used"""
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
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new_callable=AsyncMock,
               return_value=mock_pool) as mock_get_pool:
        result = await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        # Verify pool was requested
        mock_get_pool.assert_called_once()
        assert result.success is True


@pytest.mark.asyncio
async def test_connection_pool_settings_passed(db_service):
    """Test that pool configuration settings are passed correctly"""
    from config import settings
    
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
    
    with patch('services.db_connection_service.pool_manager.get_pool',
               new_callable=AsyncMock,
               return_value=mock_pool) as mock_get_pool:
        await db_service.test_connection("postgres://user:pass@localhost:5432/db")
        
        # Verify pool settings were passed from config - resilient to parameter order
        mock_get_pool.assert_called_once()
        _, kwargs = mock_get_pool.call_args
        assert kwargs.get("min_size") == settings.db_pool_min_size
        assert kwargs.get("max_size") == settings.db_pool_max_size
        assert kwargs.get("timeout") == settings.db_pool_timeout
