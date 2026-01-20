import sys
import os
import logging
from io import StringIO

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService

# Test that credentials don't leak in logs
def test_no_credentials_in_logs():
    """Verify that connection URLs with credentials are not logged"""
    
    # Capture log output
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.ERROR)
    
    logger = logging.getLogger('services.db_connection_service')
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    
    # Test with a connection URL containing credentials
    test_url = "postgres://testuser:secretpassword123@nonexistent-host.example.com:5432/testdb"
    
    # This should fail to connect (host doesn't exist)
    result = DBConnectionService.test_connection(test_url)
    
    # Get the log output
    log_output = log_stream.getvalue()
    
    # Verify the connection failed (expected)
    assert result.success is False
    
    # Verify credentials are NOT in the log output
    assert "secretpassword123" not in log_output, "Password found in logs!"
    assert test_url not in log_output, "Full connection URL found in logs!"
    
    # Verify that some error was logged (we should log errors, just not credentials)
    assert len(log_output) > 0, "No error was logged"
    assert "Database Connection Failed" in log_output
    
    # Clean up
    logger.removeHandler(handler)
    
    print("✅ PASSED: No credentials leaked in logs")
    print(f"Log output (sanitized): {log_output[:200]}...")

if __name__ == "__main__":
    test_no_credentials_in_logs()
