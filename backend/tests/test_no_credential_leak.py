import sys
import os
import logging
import pytest
from io import StringIO
from unittest.mock import patch
import psycopg

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService

@pytest.fixture
def db_service():
    """Create a DBConnectionService instance with default dependencies."""
    return DBConnectionService()



@pytest.mark.asyncio
async def test_service_sanitizes_error_logs(db_service):
    """
    Verify that DBConnectionService sanitizes credentials in error logs
    when the underlying driver raises an exception containing the URL.
    """
    # Setup log capture
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger('services.db_connection_service')
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    
    url = "postgres://user:supersecret@1.2.3.4:5432/db"
    
    # Mock pool_manager.get_pool to raise an OperationalError containing the URL
    # This simulates a scenario where the driver returns the connection string in the error.
    error_msg = f"FATAL: password authentication failed for {url}"
    
    with patch('services.db_connection_service.pool_manager.get_pool', side_effect=psycopg.OperationalError(error_msg)):
        result = await db_service.test_connection(url)
        
        assert result.success is False
        
        logs = log_stream.getvalue()
        
        # Verify the password is NOT in the logs
        assert "supersecret" not in logs, "Password leaked in logs!"
        
        # Verify the masked version IS in the logs
        assert "user:******@" in logs, "Sanitization did not occur in logs!"
        
    # Cleanup
    logger.removeHandler(handler)
    print("✅ PASSED: No credentials leaked in logs")

if __name__ == "__main__":
    test_service_sanitizes_error_logs()
