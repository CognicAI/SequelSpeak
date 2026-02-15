"""
Shared pytest configuration and fixtures for all tests.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from main import app, prom_metrics
from config import settings


@pytest.fixture(scope="session", autouse=True)
def initialize_test_metrics():
    """
    Initialize metrics once for the entire test session.
    This ensures metrics are properly set up before any tests run.
    """
    if settings.metrics_enabled and prom_metrics:
        prom_metrics.initialize_metrics()


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
async def client(reset_conversation_state):
    """
    Provide an async test client for each test.
    
    Uses the session-scoped event loop but creates a new client instance
    for each test to ensure test isolation.
    
    Note: ASGITransport with app triggers lifespan events by default.
    Depends on reset_conversation_state to ensure proper initialization order.
    """
    # Create transport with raise_app_exceptions=False to match test expectations
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
