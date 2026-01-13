import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# Add backend to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService
import psycopg

def test_connection_success():
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
        
        assert result["success"] == True
        assert result["message"] == "Connection successful!"

def test_connection_operational_error_sanitization():
    # Simulate a sensitive DB error
    with patch('psycopg.connect', side_effect=psycopg.OperationalError("Sensitive internal DB info: password mismatch for user 'admin'")):
        
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        
        assert result["success"] == False
        # Verify the message is SANITIZED
        assert "Sensitive internal DB info" not in result["message"]
        assert result["message"] == "Connection Failed: Unable to connect to the database. Please verify your host, port, and credentials."

def test_connection_generic_error():
    with patch('psycopg.connect', side_effect=Exception("Total failure")):
        result = DBConnectionService.test_connection("postgres://user:pass@localhost:5432/db")
        assert result["success"] == False
        assert result["message"] == "An unexpected error occurred while testing the connection."
