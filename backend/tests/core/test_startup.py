import pytest
import os
import sys

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from httpx import ASGITransport, AsyncClient
from main import app


# Note: client fixture is provided by tests/conftest.py


@pytest.mark.asyncio
async def test_startup_successful(client):
    """Verify app starts up successfully with current config."""
    # Trigger startup by making a request
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
