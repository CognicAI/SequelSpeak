import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# Add backend to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService
import psycopg
from unittest.mock import patch as config_patch

# ============================================================================
# SUCCESSFUL CONNECTION TESTS
# ============================================================================

def test_connection_success():
    """Test successful database connection"""
    # Mock psycopg.connect
    with patch('psycopg.connect') as mock_connect:
        # Configure the mock context manager
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Configure the execute/fetchone result
        mock_cursor.fetchone.return_value = (1,)

        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"]  is True
        assert result["message"] == "Connection successful!"

# ============================================================================
# AUTHENTICATION ERROR TESTS
# ============================================================================

def test_connection_authentication_failed():
    """Test authentication failure with password mismatch"""
    error_msg = "password authentication failed for user \"testuser\""
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"]  is False
        assert "Authentication error" in result["message"]
        assert "testuser" not in result["message"]  # Username should not leak
        assert "verify your username, password" in result["message"]

def test_connection_no_pg_hba_entry():
    """Test pg_hba.conf access denial"""
    error_msg = "no pg_hba.conf entry for host \"192.168.1.100\""
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@192.168.1.100:5432/db")
        
        assert result["success"]  is False
        assert "Authentication error" in result["message"]
        assert "access permissions" in result["message"]

def test_connection_permission_denied():
    """Test permission denied error"""
    error_msg = "permission denied for database \"restricted_db\""
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/restricted_db")
        
        assert result["success"]  is False
        assert "Authentication error" in result["message"]

# ============================================================================
# DATABASE NOT FOUND TESTS
# ============================================================================

def test_connection_database_not_found():
    """Test database does not exist error"""
    error_msg = "database \"nonexistent_db\" does not exist"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/nonexistent_db")
        
        assert result["success"]  is False
        assert "database could not be found" in result["message"]
        assert "verify the database name" in result["message"]
        assert "nonexistent_db" not in result["message"]  # DB name should not leak

# ============================================================================
# NETWORK/CONNECTIVITY ERROR TESTS
# ============================================================================

def test_connection_refused():
    """Test connection refused (server not running)"""
    error_msg = "connection refused"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"]  is False
        assert "Unable to reach the database server" in result["message"]
        assert "verify the host, port" in result["message"]

def test_connection_host_not_found():
    """Test DNS resolution failure"""
    error_msg = "could not translate host name \"invalid-host.example.com\" to address"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@invalid-host.example.com:5432/db")
        
        assert result["success"]  is False
        assert "Unable to reach the database server" in result["message"]
        assert "invalid-host.example.com" not in result["message"]  # Host should not leak

def test_connection_network_unreachable():
    """Test network unreachable error"""
    error_msg = "network is unreachable"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@10.0.0.1:5432/db")
        
        assert result["success"]  is False
        assert "Unable to reach the database server" in result["message"]

def test_connection_could_not_connect():
    """Test generic could not connect error"""
    error_msg = "could not connect to server: Connection timed out"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@remote.example.com:5432/db")
        
        assert result["success"]  is False
        assert "Unable to reach the database server" in result["message"]

# ============================================================================
# TIMEOUT ERROR TESTS
# ============================================================================

def test_connection_timeout_error():
    """Test connection timeout"""
    # Simulate a timeout error
    with patch('psycopg.connect', side_effect=psycopg.OperationalError("connection timeout expired")):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"]  is False
        # Verify timeout-specific message
        assert "timed out" in result["message"]
        assert "10 seconds" in result["message"]  # Default timeout
        assert "postgres://" not in result["message"]  # No URL in message

def test_connection_timeout_timed_out():
    """Test alternative timeout error message"""
    error_msg = "server closed the connection unexpectedly: timeout timed out"
    with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
        result = DBConnectionService.test_connection("postgres://user:pass@slow-server.com:5432/db")
        
        assert result["success"]  is False
        assert "timed out" in result["message"]
        assert "10 seconds" in result["message"]

# ============================================================================
# ERROR SANITIZATION TESTS
# ============================================================================

def test_connection_operational_error_sanitization():
    """Test that sensitive information is sanitized from error messages"""
    # Simulate a sensitive DB error
    with patch('psycopg.connect', side_effect=psycopg.OperationalError("Sensitive internal DB info: password mismatch for user 'admin'")):
        
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"]  is False
        # Verify the message is SANITIZED
        assert "Sensitive internal DB info" not in result["message"]
        assert "Connection failed: Unable to connect to the database" in result["message"]
        assert "password mismatch" not in result["message"]

def test_connection_error_no_credentials_leak():
    """Test that connection URLs with credentials never appear in error messages"""
    sensitive_url = "postgres://admin:supersecret123@prod-db.example.com:5432/production"
    
    with patch('psycopg.connect', side_effect=psycopg.OperationalError("Connection failed")):
        result = DBConnectionService.test_connection(sensitive_url)
        
        assert result["success"]  is False
        # Verify NO part of the URL appears in the message
        assert "supersecret123" not in result["message"]
        assert "admin" not in result["message"]
        assert "prod-db.example.com" not in result["message"]
        assert sensitive_url not in result["message"]

# ============================================================================
# GENERIC ERROR TESTS
# ============================================================================

def test_connection_generic_error():
    """Test generic unexpected error handling"""
    with patch('psycopg.connect', side_effect=Exception("Total failure")):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        assert result["success"]  is False
        assert result["message"] == "An unexpected error occurred while testing the connection."

def test_connection_value_error():
    """Test ValueError handling"""
    with patch('psycopg.connect', side_effect=ValueError("Invalid connection parameter")):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        assert result["success"]  is False
        assert "unexpected error" in result["message"]

def test_connection_type_error():
    """Test TypeError handling"""
    with patch('psycopg.connect', side_effect=TypeError("Type mismatch")):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        assert result["success"]  is False
        assert "unexpected error" in result["message"]

