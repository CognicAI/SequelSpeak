import sys
import os
import pytest

# Add backend to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService

def test_parse_and_verify_url_valid():
    url = "postgres://user:pass@localhost:5432/db"
    result = DBConnectionService.parse_and_verify_url(url)
    assert result["valid"] == True

def test_parse_and_verify_url_invalid_scheme():
    url = "mysql://user:pass@localhost:5432/db"
    result = DBConnectionService.parse_and_verify_url(url)
    assert result["valid"] == False
    assert "Invalid URL scheme" in result["message"]

def test_parse_and_verify_url_missing_host():
    # URL parsing might interpret parts differently depending on missing components,
    # but strictly missing netloc is invalid for us.
    url = "postgres:///dbname" 
    result = DBConnectionService.parse_and_verify_url(url)
    # This might be valid for local socket connections in some libpq versions, 
    # but our simple validator checks for netloc (host).
    # urlparse("postgres:///dbname").netloc is empty string.
    assert result["valid"] == False
    assert "Host is missing" in result["message"]

# Note: We cannot easily unit test test_connection success without a real DB or mocking psycopg.
# For now, we trust the integration or manual verification for true connectivity.
