"""
Tests for the ErrorClassifier class to verify error classification logic.
This test suite ensures the refactored error handling maintains the same behavior.
"""
import sys
import os

# Add backend to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import ErrorClassifier
from schemas.errors import ErrorCode
import pytest


@pytest.fixture
def error_classifier():
    """Create an ErrorClassifier instance for testing."""
    return ErrorClassifier()


class TestErrorClassifier:
    """Test suite for ErrorClassifier class"""
    
    def test_auth_failed_password_error(self, error_classifier):
        """Test classification of password authentication failure"""
        error_msg = "password authentication failed for user \"testuser\""
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.AUTH_FAILED
        assert "Authentication error" in message
        assert "username, password, and access permissions" in message
    
    def test_auth_failed_no_pg_hba(self, error_classifier):
        """Test classification of pg_hba.conf entry missing"""
        error_msg = "no pg_hba.conf entry for host \"192.168.1.100\""
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.AUTH_FAILED
        assert "Authentication error" in message
    
    def test_auth_failed_permission_denied(self, error_classifier):
        """Test classification of permission denied error"""
        error_msg = "permission denied for database \"restricted_db\""
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.AUTH_FAILED
        assert "Authentication error" in message
    
    def test_database_not_found(self, error_classifier):
        """Test classification of database does not exist error"""
        error_msg = "database \"nonexistent_db\" does not exist"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.DATABASE_NOT_FOUND
        assert "database could not be found" in message
        assert "verify the database name" in message
    
    def test_database_not_found_alternate(self, error_classifier):
        """Test classification of alternate database not found message"""
        error_msg = "FATAL:  database \"mydb\" does not exist"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.DATABASE_NOT_FOUND
        assert "database could not be found" in message
    
    def test_ssl_error_certificate_verify(self, error_classifier):
        """Test classification of SSL certificate verification error"""
        error_msg = "SSL certificate verify failed"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.SSL_ERROR
        assert "SSL/TLS certificate error" in message
        assert "certificate validity" in message
    
    def test_ssl_error_self_signed(self, error_classifier):
        """Test classification of self-signed certificate error"""
        error_msg = "self-signed certificate in certificate chain"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.SSL_ERROR
        assert "SSL/TLS certificate error" in message
    
    def test_ssl_error_expired(self, error_classifier):
        """Test classification of expired certificate error"""
        error_msg = "certificate expired"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.SSL_ERROR
        assert "SSL/TLS certificate error" in message
    
    def test_timeout_expired(self, error_classifier):
        """Test classification of timeout error"""
        error_msg = "connection timeout expired"
        error_code, message = error_classifier.classify_error(error_msg, 15)
        
        assert error_code == ErrorCode.TIMEOUT
        assert "timed out after 15 seconds" in message
        assert "verify the host, port, and network connectivity" in message
    
    def test_timeout_timed_out(self, error_classifier):
        """Test classification of alternate timeout message"""
        error_msg = "timeout timed out"
        error_code, message = error_classifier.classify_error(error_msg, 20)
        
        assert error_code == ErrorCode.TIMEOUT
        assert "timed out after 20 seconds" in message
    
    def test_connection_refused(self, error_classifier):
        """Test classification of connection refused error"""
        error_msg = "connection refused"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.HOST_UNREACHABLE
        assert "Unable to reach the database server" in message
        assert "verify the host, port, and network connectivity" in message
    
    def test_could_not_connect_to_server(self, error_classifier):
        """Test classification of could not connect error"""
        error_msg = "could not connect to server"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.HOST_UNREACHABLE
        assert "Unable to reach the database server" in message
    
    def test_ssl_syscall_error(self, error_classifier):
        """Test classification of SSL SYSCALL error (network error during SSL)"""
        error_msg = "SSL SYSCALL error: Connection reset by peer"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.HOST_UNREACHABLE
        assert "Unable to reach the database server" in message
    
    def test_could_not_translate_hostname(self, error_classifier):
        """Test classification of DNS resolution failure"""
        error_msg = "could not translate host name \"invalid-host.example.com\" to address"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.HOST_UNREACHABLE
        assert "Unable to reach the database server" in message
    
    def test_network_unreachable(self, error_classifier):
        """Test classification of network unreachable error"""
        error_msg = "network is unreachable"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.HOST_UNREACHABLE
        assert "Unable to reach the database server" in message
    
    def test_generic_error_fallback(self, error_classifier):
        """Test fallback to generic error for unknown error messages"""
        error_msg = "Some unknown database error occurred"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.CONNECTION_ERROR
        assert "Connection failed: Unable to connect to the database" in message
        assert "verify your host, port, database name, and credentials" in message
    
    def test_case_insensitive_matching(self, error_classifier):
        """Test that error matching is case-insensitive"""
        error_msg = "PASSWORD AUTHENTICATION FAILED FOR USER \"test\""
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.AUTH_FAILED
        assert "Authentication error" in message
    
    def test_regex_pattern_matching(self, error_classifier):
        """Test that regex patterns work correctly for database not found"""
        # Test "does not exist" before "database"
        error_msg1 = "database \"test\" does not exist"
        error_code1, _ = error_classifier.classify_error(error_msg1, 10)
        assert error_code1 == ErrorCode.DATABASE_NOT_FOUND
        
        # Test "database" before "does not exist"
        error_msg2 = "FATAL: database \"test\" does not exist"
        error_code2, _ = error_classifier.classify_error(error_msg2, 10)
        assert error_code2 == ErrorCode.DATABASE_NOT_FOUND
    
    def test_multiple_keywords_in_error(self, error_classifier):
        """Test that the first matching pattern wins when multiple keywords exist"""
        # This error could match both auth and database patterns
        # but should match auth first (as it appears first in ERROR_PATTERNS)
        error_msg = "authentication failed for database that does not exist"
        error_code, message = error_classifier.classify_error(error_msg, 10)
        
        assert error_code == ErrorCode.AUTH_FAILED
        assert "Authentication error" in message
