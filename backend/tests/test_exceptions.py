import sys
import os
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import patch

# Add backend to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import DatabaseConnectionError
from schemas.errors import ErrorCode
from main import app

# Create test client
client = TestClient(app)

# ============================================================================
# UNIT TESTS: DatabaseConnectionError Exception Class
# ============================================================================

class TestDatabaseConnectionError:
    """Unit tests for the DatabaseConnectionError exception class."""
    
    def test_init_with_detail_only(self):
        """Test initialization with only detail message."""
        detail = "Connection failed"
        exc = DatabaseConnectionError(detail=detail)
        
        assert exc.detail == detail
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.error_code is None
    
    def test_init_with_detail_and_error_code(self):
        """Test initialization with detail and error_code."""
        detail = "Authentication failed"
        error_code = ErrorCode.AUTH_FAILED
        exc = DatabaseConnectionError(detail=detail, error_code=error_code)
        
        assert exc.detail == detail
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.error_code == error_code
    
    def test_inherits_from_http_exception(self):
        """Test that DatabaseConnectionError properly inherits from HTTPException."""
        from fastapi import HTTPException
        
        exc = DatabaseConnectionError(detail="Test error")
        assert isinstance(exc, HTTPException)
    
    def test_status_code_always_400(self):
        """Test that status_code is always 400 regardless of initialization."""
        test_cases = [
            DatabaseConnectionError(detail="Error 1"),
            DatabaseConnectionError(detail="Error 2", error_code=ErrorCode.TIMEOUT),
            DatabaseConnectionError(detail="Error 3", error_code=ErrorCode.HOST_UNREACHABLE),
        ]
        
        for exc in test_cases:
            assert exc.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_all_error_codes(self):
        """Test initialization with all available ErrorCode enum values."""
        error_codes = [
            ErrorCode.AUTH_FAILED,
            ErrorCode.DATABASE_NOT_FOUND,
            ErrorCode.HOST_UNREACHABLE,
            ErrorCode.TIMEOUT,
            ErrorCode.SSL_ERROR,
            ErrorCode.INVALID_URL,
            ErrorCode.CONNECTION_ERROR,
        ]
        
        for error_code in error_codes:
            exc = DatabaseConnectionError(
                detail=f"Test error for {error_code.value}",
                error_code=error_code
            )
            assert exc.error_code == error_code
            assert exc.detail == f"Test error for {error_code.value}"
    
    def test_detail_message_preserved(self):
        """Test that detail message is preserved exactly as provided."""
        test_messages = [
            "Simple error",
            "Error with special chars: @#$%",
            "Multi-line\nerror\nmessage",
            "Error with unicode: 你好",
            "",  # Empty string
        ]
        
        for message in test_messages:
            exc = DatabaseConnectionError(detail=message)
            assert exc.detail == message
    
    def test_error_code_optional(self):
        """Test that error_code parameter is truly optional."""
        # Should not raise any exception
        exc = DatabaseConnectionError(detail="Test")
        assert exc.error_code is None


# ============================================================================
# INTEGRATION TESTS: Exception Handler
# ============================================================================

class TestDatabaseConnectionErrorHandler:
    """Integration tests for the database_connection_error_handler."""
    
    @pytest.mark.asyncio
    async def test_handler_with_error_code(self):
        """Test exception handler converts exception with error_code to JSON response."""
        # We need to trigger the exception handler through an actual endpoint
        # Since we don't have a direct endpoint that raises this exception in the test,
        # we'll test the handler function directly
        from main import database_connection_error_handler
        from fastapi import Request
        
        # Create a mock request
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
        
        # Create exception with error code
        exc = DatabaseConnectionError(
            detail="Database not found",
            error_code=ErrorCode.DATABASE_NOT_FOUND
        )
        
        # Call handler (await since it's async)
        response = await database_connection_error_handler(request, exc)
        
        # Verify response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.body is not None
        
        # Parse response content
        import json
        content = json.loads(response.body.decode())
        assert content["detail"] == "Database not found"
        assert content["error_code"] == ErrorCode.DATABASE_NOT_FOUND.value
    
    @pytest.mark.asyncio
    async def test_handler_without_error_code(self):
        """Test exception handler converts exception without error_code to JSON response."""
        from main import database_connection_error_handler
        from fastapi import Request
        
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
        exc = DatabaseConnectionError(detail="Generic connection error")
        
        response = await database_connection_error_handler(request, exc)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        import json
        content = json.loads(response.body.decode())
        assert content["detail"] == "Generic connection error"
        assert content["error_code"] is None
    
    @pytest.mark.asyncio
    async def test_handler_preserves_status_code(self):
        """Test that handler preserves the exception's status code."""
        from main import database_connection_error_handler
        from fastapi import Request
        
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
        exc = DatabaseConnectionError(
            detail="Test error",
            error_code=ErrorCode.TIMEOUT
        )
        
        response = await database_connection_error_handler(request, exc)
        
        # Should be 400 as defined in DatabaseConnectionError
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.status_code == exc.status_code
    
    @pytest.mark.asyncio
    async def test_handler_response_structure(self):
        """Test that handler response matches expected schema structure."""
        from main import database_connection_error_handler
        from fastapi import Request
        
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
        exc = DatabaseConnectionError(
            detail="SSL certificate verification failed",
            error_code=ErrorCode.SSL_ERROR
        )
        
        response = await database_connection_error_handler(request, exc)
        
        import json
        content = json.loads(response.body.decode())
        
        # Verify structure matches ConnectionErrorDetail schema
        assert "detail" in content
        assert "error_code" in content
        assert isinstance(content["detail"], str)
        assert isinstance(content["error_code"], str)
        assert len(content) == 2  # Only these two fields
    
    @pytest.mark.asyncio
    async def test_handler_with_all_error_codes(self):
        """Test handler with all possible ErrorCode values."""
        from main import database_connection_error_handler
        from fastapi import Request
        
        error_codes = [
            ErrorCode.AUTH_FAILED,
            ErrorCode.DATABASE_NOT_FOUND,
            ErrorCode.HOST_UNREACHABLE,
            ErrorCode.TIMEOUT,
            ErrorCode.SSL_ERROR,
            ErrorCode.INVALID_URL,
            ErrorCode.CONNECTION_ERROR,
        ]
        
        for error_code in error_codes:
            request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
            exc = DatabaseConnectionError(
                detail=f"Error: {error_code.value}",
                error_code=error_code
            )
            
            response = await database_connection_error_handler(request, exc)
            
            import json
            content = json.loads(response.body.decode())
            
            assert content["error_code"] == error_code.value
            assert content["detail"] == f"Error: {error_code.value}"
    
    @pytest.mark.asyncio
    async def test_handler_special_characters_in_detail(self):
        """Test handler properly handles special characters in detail message."""
        from main import database_connection_error_handler
        from fastapi import Request
        
        special_messages = [
            "Error with quotes: 'single' and \"double\"",
            "Error with symbols: @#$%^&*()",
            "Error with unicode: 你好世界",
            "Error with newline\nand\ttab",
        ]
        
        for message in special_messages:
            request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
            exc = DatabaseConnectionError(detail=message)
            
            response = await database_connection_error_handler(request, exc)
            
            import json
            content = json.loads(response.body.decode())
            
            assert content["detail"] == message


# ============================================================================
# END-TO-END TESTS: Exception Handler Through API Endpoint
# ============================================================================

class TestExceptionHandlerEndToEnd:
    """End-to-end tests verifying exception handler works through actual API calls."""
    
    def test_connection_endpoint_invalid_url_triggers_handler(self):
        """Test that invalid URL in connection endpoint triggers the exception handler."""
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "invalid://url"}
        )
        
        # Should get 400 status
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Response should have the expected structure
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == ErrorCode.INVALID_URL.value
    
    def test_connection_endpoint_missing_host_triggers_handler(self):
        """Test that URL with missing host triggers the exception handler."""
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgres:///dbname"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == ErrorCode.INVALID_URL.value
        assert "Host is missing" in data["detail"]
    
    def test_connection_endpoint_wrong_scheme_triggers_handler(self):
        """Test that wrong URL scheme triggers the exception handler."""
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "mysql://user:pass@localhost:5432/db"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == ErrorCode.INVALID_URL.value
        assert "Invalid URL scheme" in data["detail"]
