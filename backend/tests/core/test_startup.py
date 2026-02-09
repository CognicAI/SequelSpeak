import pytest
import os
import sys

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_startup_successful():
    """Verify app starts up successfully with current config."""
    # Trigger startup by making a request
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
