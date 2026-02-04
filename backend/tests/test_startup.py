import pytest
import os
import sys
from fastapi.testclient import TestClient

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

def test_startup_successful():
    """Verify app starts up successfully with current config."""
    # Trigger startup by making a request
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
