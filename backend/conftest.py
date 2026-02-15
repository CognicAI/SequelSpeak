"""
Pytest configuration for SequelSpeak backend tests.
"""
import sys
import os

# Add backend directory to Python path FIRST (before any imports)
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# MUST be set BEFORE any imports from the project
os.environ['RATE_LIMIT_ENABLED'] = 'False'
os.environ['CLERK_SECRET_KEY'] = 'test_clerk_secret_key_for_testing'  # Mock Clerk secret for tests

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict
import jwt


# ============================================================================
# Authentication Test Fixtures
# ============================================================================

@pytest.fixture
def mock_clerk_secret_key():
    """Mock Clerk secret key for testing JWT verification."""
    # Must match the secret set in os.environ['CLERK_SECRET_KEY'] above
    return "test_clerk_secret_key_for_testing"


@pytest.fixture
def mock_valid_jwt(mock_clerk_secret_key):
    """
    Generate a mock valid JWT token for testing authenticated endpoints.
    
    Returns a JWT token that matches the structure Clerk would provide:
    - sub: User ID (Clerk user identifier)
    - email: User email address
    - exp: Token expiration (1 hour from now)
    - iat: Token issued at (now)
    - iss: Token issuer (mock Clerk instance)
    """
    payload = {
        "sub": "user_test_2abc3def4ghi5jkl",
        "email": "test@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "iss": "https://clerk.test.sequelspeak.com",
    }
    # Use HS256 for simplicity in tests (Clerk uses RS256 in production)
    return jwt.encode(payload, mock_clerk_secret_key, algorithm="HS256")


@pytest.fixture
def mock_expired_jwt(mock_clerk_secret_key):
    """
    Generate an expired JWT token for testing expired token handling.
    
    Token expired 1 hour ago, should trigger 401 Unauthorized response.
    """
    payload = {
        "sub": "user_test_2abc3def4ghi5jkl",
        "email": "test@example.com",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "iss": "https://clerk.test.sequelspeak.com",
    }
    return jwt.encode(payload, mock_clerk_secret_key, algorithm="HS256")


@pytest.fixture
def mock_invalid_signature_jwt():
    """
    Generate a JWT token with invalid signature for testing verification failure.
    
    Uses a different secret key, so signature verification should fail.
    """
    payload = {
        "sub": "user_test_2abc3def4ghi5jkl",
        "email": "test@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "iss": "https://clerk.test.sequelspeak.com",
    }
    # Use wrong secret key to create invalid signature
    wrong_secret = "wrong_secret_key_should_fail_verification"
    return jwt.encode(payload, wrong_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
async def reset_conversation_state():
    """
    Reset conversation state manager before and after each test.
    
    This ensures Redis clients are properly closed and recreated
    in the current event loop, preventing 'Future attached to different loop' errors.
    """
    from services.conversation_state import conversation_state_manager
    
    # Close any existing Redis connection before test
    await conversation_state_manager.close()
    
    yield
    
    # Close connection after test for cleanup
    await conversation_state_manager.close()


@pytest.fixture
def auth_headers(mock_valid_jwt) -> Dict[str, str]:
    """
    Generate Authorization headers with valid JWT token.
    
    Use this fixture for authenticated endpoint tests:
        def test_protected_endpoint(client, auth_headers):
            response = client.post("/api/v1/endpoint", json={...}, headers=auth_headers)
    """
    return {"Authorization": f"Bearer {mock_valid_jwt}"}


@pytest.fixture
def expired_auth_headers(mock_expired_jwt) -> Dict[str, str]:
    """Generate Authorization headers with expired JWT token."""
    return {"Authorization": f"Bearer {mock_expired_jwt}"}


@pytest.fixture
def invalid_auth_headers(mock_invalid_signature_jwt) -> Dict[str, str]:
    """Generate Authorization headers with invalid signature JWT token."""
    return {"Authorization": f"Bearer {mock_invalid_signature_jwt}"}

