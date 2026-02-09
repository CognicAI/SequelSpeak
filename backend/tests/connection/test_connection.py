import sys
import os
import pytest

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
# VALID URL TESTS
# ============================================================================

def test_parse_and_verify_url_valid(db_service):
    """Test basic valid postgres:// URL"""
    url = "postgres://user:pass@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_postgresql_scheme(db_service):
    """Test postgresql:// scheme (alternative to postgres://)"""
    url = "postgresql://user:pass@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True
    assert result.message == "Valid structure"

def test_parse_url_without_port(db_service):
    """Test URL without explicit port (should use default 5432)"""
    url = "postgres://user:pass@localhost/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_with_special_chars_in_password(db_service):
    """Test password with special characters: @, :, /, %, #, etc."""
    # URL-encoded special characters in password
    test_cases = [
        "postgres://user:p%40ss@localhost:5432/db",  # @ symbol
        "postgres://user:p%3Ass@localhost:5432/db",  # : symbol
        "postgres://user:p%2Fss@localhost:5432/db",  # / symbol
        "postgres://user:p%23ss@localhost:5432/db",  # # symbol
        "postgres://user:p%25ss@localhost:5432/db",  # % symbol
        "postgres://user:complex%21%40%23pass@localhost:5432/db",  # !@#
    ]
    
    for url in test_cases:
        result = db_service.parse_and_verify_url(url)
        assert result.success is True, f"Failed for URL: {url}"

def test_parse_url_with_special_chars_in_username(db_service):
    """Test username with special characters"""
    url = "postgres://user%2Bname@localhost:5432/db"  # user+name
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_with_special_chars_in_dbname(db_service):
    """Test database name with special characters"""
    url = "postgres://user:pass@localhost:5432/my%2Ddb"  # my-db
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_ipv6_host(db_service):
    """Test IPv6 address as host"""
    url = "postgres://user:pass@[::1]:5432/db"  # IPv6 localhost
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_with_domain(db_service):
    """Test URL with domain name"""
    url = "postgres://user:pass@db.example.com:5432/mydb"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_with_subdomain(db_service):
    """Test URL with subdomain"""
    url = "postgres://user:pass@prod.db.example.com:5432/mydb"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

# ============================================================================
# INVALID URL TESTS
# ============================================================================

def test_parse_and_verify_url_invalid_scheme(db_service):
    """Test invalid URL scheme (mysql instead of postgres)"""
    url = "mysql://user:pass@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is False
    assert "Invalid URL scheme" in result.message
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_url_http_scheme(db_service):
    """Test HTTP scheme (should be rejected)"""
    url = "http://user:pass@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is False
    assert "Invalid URL scheme" in result.message
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_and_verify_url_missing_host(db_service):
    """Test URL with missing host"""
    # URL parsing might interpret parts differently depending on missing components,
    # but strictly missing netloc is invalid for us.
    url = "postgres:///dbname" 
    result = db_service.parse_and_verify_url(url)
    # This might be valid for local socket connections in some libpq versions, 
    # but our simple validator checks for netloc (host).
    # urlparse("postgres:///dbname").netloc is empty string.
    assert result.success is False
    assert "Host is missing" in result.message
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_url_empty_string(db_service):
    """Test empty URL string"""
    url = ""
    result = db_service.parse_and_verify_url(url)
    assert result.success is False
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_url_no_scheme(db_service):
    """Test URL without scheme"""
    url = "user:pass@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is False
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_url_malformed(db_service):
    """Test completely malformed URL"""
    url = "not a valid url at all"
    result = db_service.parse_and_verify_url(url)
    assert result.success is False
    assert result.error_code == ErrorCode.INVALID_URL

def test_parse_url_missing_credentials(db_service):
    """Test URL without username/password (should still be valid structurally)"""
    url = "postgres://localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    # This is structurally valid, even if it might fail to connect
    assert result.success is True

# Note: Port validation is typically handled by psycopg during connection,
# not during URL parsing. The urlparse function accepts any port value.
# We test that the URL structure is valid, actual port validation happens at connection time.

def test_parse_url_with_query_params(db_service):
    """Test URL with connection parameters"""
    url = "postgres://user:pass@localhost:5432/db?sslmode=require"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

# ============================================================================
# EDGE CASES
# ============================================================================

def test_parse_url_localhost_variations(db_service):
    """Test various localhost representations"""
    urls = [
        "postgres://user:pass@localhost:5432/db",
        "postgres://user:pass@127.0.0.1:5432/db",
        "postgres://user:pass@[::1]:5432/db",  # IPv6 localhost
    ]
    
    for url in urls:
        result = db_service.parse_and_verify_url(url)
        assert result.success is True, f"Failed for URL: {url}"

def test_parse_url_different_ports(db_service):
    """Test various valid port numbers"""
    ports = [5432, 5433, 5434, 15432, 65535]
    
    for port in ports:
        url = f"postgres://user:pass@localhost:{port}/db"
        result = db_service.parse_and_verify_url(url)
        assert result.success is True, f"Failed for port: {port}"

def test_parse_url_long_password(db_service):
    """Test URL with very long password"""
    long_password = "a" * 100
    url = f"postgres://user:{long_password}@localhost:5432/db"
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

def test_parse_url_unicode_in_password(db_service):
    """Test URL with unicode characters in password (URL-encoded)"""
    # Unicode characters should be URL-encoded
    url = "postgres://user:p%C3%A4ss@localhost:5432/db"  # pässword
    result = db_service.parse_and_verify_url(url)
    assert result.success is True

