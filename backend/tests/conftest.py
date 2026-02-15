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


@pytest.fixture
async def client():
    """
    Provide an async test client for each test.
    
    Uses the session-scoped event loop but creates a new client instance
    for each test to ensure test isolation.
    
    Note: ASGITransport with app triggers lifespan events by default.
    """
    # Create transport with raise_app_exceptions=False to match test expectations
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
