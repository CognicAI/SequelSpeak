"""
Shared pytest configuration and fixtures for all tests.
"""
import pytest
from typing import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from main import app, prom_metrics
from config import settings
from utils.auth import verify_clerk_token


@pytest.fixture(scope="session", autouse=True)
def initialize_test_metrics():
    """
    Initialize metrics once for the entire test session.
    This ensures metrics are properly set up before any tests run.
    """
    if settings.metrics_enabled and prom_metrics:
        prom_metrics.initialize_metrics()


@pytest.fixture(autouse=True)
async def reset_conversation_state() -> AsyncGenerator[None, None]:
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
async def client(reset_conversation_state: None) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async test client for each test.

    Uses the session-scoped event loop but creates a new client instance
    for each test to ensure test isolation.

    Note: ASGITransport with app triggers lifespan events by default.
    Depends on reset_conversation_state to ensure proper initialization order.

    Auth note: verify_clerk_token is overridden with a mock so tests never
    hit the real Clerk service. The mock returns a fake claims dict with a
    predictable sub (user ID) for assertion purposes.
    """
    # Override Clerk JWT auth for all tests – avoids real Clerk network calls
    async def mock_verify_clerk_token():
        return {"sub": "test-user-id-00000000", "email": "test@example.com"}

    app.dependency_overrides[verify_clerk_token] = mock_verify_clerk_token

    try:
        # Manually trigger lifespan to initialize router service and other components
        async with app.router.lifespan_context(app):
            # Create transport with raise_app_exceptions=False to match test expectations
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
    finally:
        # Always clean up the override after the test
        app.dependency_overrides.pop(verify_clerk_token, None)
