import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_health_mock():
    """
    Verify that the /health endpoint returns the exact JSON structure
    defined in the parallel-safe developer contract.
    """
    response = client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    
    # Assert top-level fields
    assert "status" in data
    assert "database" in data
    
    # Assert frozen mock values
    assert data["status"] == "UP"
    assert data["database"]["connected"] is True
    
    # Assert no extra fields as per parallel usage rules
    assert len(data) == 2
    assert len(data["database"]) == 1
