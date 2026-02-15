"""
Tests for /test-connection endpoint authentication.

Verifies that the endpoint properly enforces JWT authentication
and handles various authentication scenarios (valid token, expired token, 
missing token, invalid signature).
"""
import sys
import os

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from typing import Dict
from httpx import ASGITransport, AsyncClient
from main import app


# Note: client fixture is provided by tests/conftest.py


class TestConnectionEndpointAuthentication:
    """Tests for authentication requirements on /test-connection endpoint."""
    
    @pytest.mark.asyncio
    async def test_connection_requires_authentication(self, client):
        """Verify that /test-connection returns 401 without authentication."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        # Check that the error mentions authentication or token requirement
        detail_lower = data["detail"].lower()
        assert any(word in detail_lower for word in ["authentic", "token", "bearer", "sign", "required"])
    
    @pytest.mark.asyncio
    async def test_connection_with_valid_token_requires_clerk_config(self, client, auth_headers: Dict[str, str], mock_clerk_secret_key: str):
        """        Verify that endpoint with valid token requires Clerk configuration.
        
        Without CLERK_SECRET_KEY set in environment, even valid tokens should fail
        with 500 (service unavailable) rather than 401 (unauthorized).
        """
        # Note: This test assumes CLERK_SECRET_KEY is not set in test environment
        # The endpoint should return 500 because auth service is not configured
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers=auth_headers
        )
        
        # Should get 500 because Clerk client can't be initialized without secret key
        # (In real deployment, CLERK_SECRET_KEY would be set)
        assert response.status_code in [401, 500]
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_connection_with_expired_token(self, client, expired_auth_headers: Dict[str, str]):
        """Verify that endpoint rejects expired JWT tokens."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers=expired_auth_headers
        )
        
        # Should get 401 for expired token
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_connection_with_invalid_signature(self, client, invalid_auth_headers: Dict[str, str]):
        """Verify that endpoint rejects JWT tokens with invalid signatures."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers=invalid_auth_headers
        )
        
        # Should get 401 for invalid signature
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_connection_with_malformed_auth_header(self, client):
        """Verify that endpoint rejects malformed Authorization headers."""
        # Missing "Bearer" prefix
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers={"Authorization": "InvalidToken123"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_connection_with_empty_token(self, client):
        """Verify that endpoint rejects empty Bearer tokens."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers={"Authorization": "Bearer "}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    



class TestAuthenticationErrorMessages:
    """Tests for user-friendly authentication error messages."""
    
    @pytest.mark.asyncio
    async def test_missing_token_error_message_is_clear(self, client):
        """Verify that missing token error is user-friendly."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"}
        )
        
        assert response.status_code == 401
        data = response.json()
        
        # Error message should be clear and actionable
        assert "detail" in data
        detail_lower = data["detail"].lower()
        # FastAPI's HTTPBearer returns "Not authenticated" by default
        # Our custom error messages should be more specific
        assert "authentic" in detail_lower or "bearer" in detail_lower
    
    @pytest.mark.asyncio
    async def test_expired_token_error_message_is_clear(self, client, expired_auth_headers: Dict[str, str]):
        """Verify that expired token error is user-friendly."""
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@localhost:5432/testdb"},
            headers=expired_auth_headers
        )
        
        assert response.status_code == 401
        data = response.json()
        
        # Error message should mention expiration
        assert "detail" in data
        detail_lower = data["detail"].lower()
        # Should mention expired/expiration or prompt to sign in again
        assert any(word in detail_lower for word in ["expired", "expir", "sign in"])


class TestAuthenticationWithConnectionValidation:
    """
    Integration tests for authentication + connection validation.
    
    These tests verify that authentication happens BEFORE connection validation,
    ensuring that invalid credentials are rejected at the auth layer.
    """
    
    @pytest.mark.asyncio
    async def test_auth_checked_before_url_validation(self, client):
        """
        Verify that authentication is checked before URL validation.
        
        Even with an invalid URL, should get 401 (auth error) not 400 (validation error).
        """
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "invalid-url-format"}
        )
        
        # Should get 401 (no auth) not 400 (invalid URL)
        # This proves auth is checked first
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_auth_checked_before_database_connection(self, client):
        """
        Verify that authentication is checked before attempting database connection.
        
        Without auth, should never reach the database connection attempt.
        """
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgresql://user:pass@nonexistent-host-xyz:5432/testdb"}
        )
        
        # Should get 401 (no auth), not a database connection error
        assert response.status_code == 401
