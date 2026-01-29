import pytest
import os
import sys
from fastapi.testclient import TestClient

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

def test_startup_successful():
    """Verify app starts up successfully with default dev config."""
    with TestClient(app) as client:
        # Trigger startup by making a request
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
