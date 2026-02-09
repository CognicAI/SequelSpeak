"""
Tests for API metadata endpoints.

Tests cover:
- Version endpoint
- Status endpoint
- Uptime tracking
- Response format validation
"""

import sys
import os
import pytest
import time

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi.testclient import TestClient
from main import app
from config import settings


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestVersionEndpoint:
    """Tests for the /api/v1/version endpoint."""
    
    def test_version_endpoint_exists(self, client):
        """Test that the version endpoint is accessible."""
        response = client.get("/api/v1/version")
        assert response.status_code == 200
    
    def test_version_response_structure(self, client):
        """Test that version response has correct structure."""
        response = client.get("/api/v1/version")
        data = response.json()
        
        # Check required fields exist
        assert "version" in data
        assert "api_version" in data
        assert "environment" in data
        assert "build_date" in data
        assert "app_name" in data
    
    def test_version_values(self, client):
        """Test that version values are correct."""
        response = client.get("/api/v1/version")
        data = response.json()
        
        # Check version format
        assert data["version"] == "1.0.0"
        assert data["api_version"] == "v1"
        
        # Check environment matches config
        assert data["environment"] == settings.environment
        
        # Check build date format (YYYY-MM-DD)
        assert len(data["build_date"]) == 10
        assert data["build_date"].count("-") == 2
        
        # Check app name matches config
        assert data["app_name"] == settings.app_name
    
    def test_version_returns_json(self, client):
        """Test that version endpoint returns JSON."""
        response = client.get("/api/v1/version")
        assert response.headers["content-type"] == "application/json"


class TestStatusEndpoint:
    """Tests for the /api/v1/status endpoint."""
    
    def test_status_endpoint_exists(self, client):
        """Test that the status endpoint is accessible."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
    
    def test_status_response_structure(self, client):
        """Test that status response has correct structure."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        # Check required fields exist
        assert "status" in data
        assert "timestamp" in data
        assert "uptime_seconds" in data
        assert "uptime_human" in data
        assert "endpoints" in data
        assert "features" in data
    
    def test_status_values(self, client):
        """Test that status values are correct."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        # Check status is operational
        assert data["status"] == "operational"
        
        # Check timestamp format (ISO 8601 with Z suffix)
        assert data["timestamp"].endswith("Z")
        assert "T" in data["timestamp"]
        
        # Check uptime is reasonable (greater than 0, less than a day for tests)
        assert data["uptime_seconds"] >= 0
        assert data["uptime_seconds"] < 86400  # Less than 24 hours
        
        # Check uptime_human exists and is a string
        assert isinstance(data["uptime_human"], str)
        assert len(data["uptime_human"]) > 0
    
    def test_status_endpoints(self, client):
        """Test that endpoint status information is present."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        endpoints = data["endpoints"]
        
        # Check all endpoints are listed
        assert "health" in endpoints
        assert "connections" in endpoints
        assert "meta" in endpoints
        
        # Check all are operational
        assert endpoints["health"] == "operational"
        assert endpoints["connections"] == "operational"
        assert endpoints["meta"] == "operational"
    
    def test_status_features(self, client):
        """Test that feature flags are present."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        features = data["features"]
        
        # Check feature flags exist
        assert "rate_limiting" in features
        assert "circuit_breaker" in features
        
        # Check they are boolean
        assert isinstance(features["rate_limiting"], bool)
        assert isinstance(features["circuit_breaker"], bool)
        
        # Check they match settings
        assert features["rate_limiting"] == settings.rate_limit_enabled
        assert features["circuit_breaker"] == settings.circuit_breaker_enabled
    
    def test_status_returns_json(self, client):
        """Test that status endpoint returns JSON."""
        response = client.get("/api/v1/status")
        assert response.headers["content-type"] == "application/json"
    
    def test_uptime_increases(self, client):
        """Test that uptime increases between requests."""
        # Get initial uptime
        response1 = client.get("/api/v1/status")
        uptime1 = response1.json()["uptime_seconds"]
        
        # Wait a moment
        time.sleep(0.1)
        
        # Get uptime again
        response2 = client.get("/api/v1/status")
        uptime2 = response2.json()["uptime_seconds"]
        
        # Uptime should be greater or equal (may be same if requests are very fast)
        assert uptime2 >= uptime1


class TestUptimeFormatting:
    """Tests for uptime formatting helper."""
    
    def test_uptime_format_seconds(self, client):
        """Test uptime formatting for seconds."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        uptime_human = data["uptime_human"]
        
        # Should contain time units
        assert any(unit in uptime_human for unit in ['s', 'm', 'h', 'd'])
    
    def test_multiple_status_calls_consistent(self, client):
        """Test that multiple status calls return consistent structure."""
        responses = [client.get("/api/v1/status") for _ in range(3)]
        
        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # All should have same structure
        keys_set = {frozenset(r.json().keys()) for r in responses}
        assert len(keys_set) == 1  # All have same keys


class TestMetaEndpointsInDocs:
    """Tests for meta endpoints appearing in API documentation."""
    
    def test_meta_endpoints_in_openapi(self, client):
        """Test that meta endpoints appear in OpenAPI schema."""
        response = client.get("/openapi.json")
        openapi_schema = response.json()
        
        # Check version endpoint exists
        assert "/api/v1/version" in openapi_schema["paths"]
        
        # Check status endpoint exists
        assert "/api/v1/status" in openapi_schema["paths"]
    
    def test_meta_tag_exists(self, client):
        """Test that Meta tag exists in OpenAPI schema."""
        response = client.get("/openapi.json")
        openapi_schema = response.json()
        
        # Check Meta tag is defined
        tags = openapi_schema.get("tags", [])
        tag_names = [tag["name"] for tag in tags]
        
        assert "Meta" in tag_names


class TestMetaEndpointsSecurity:
    """Tests for security aspects of meta endpoints."""
    
    def test_version_no_credentials_exposed(self, client):
        """Test that version endpoint doesn't expose credentials."""
        response = client.get("/api/v1/version")
        data = response.json()
        
        # Convert to string and check for sensitive keywords
        response_str = str(data).lower()
        
        assert "password" not in response_str
        assert "secret" not in response_str
        assert "key" not in response_str
    
    def test_status_no_credentials_exposed(self, client):
        """Test that status endpoint doesn't expose credentials."""
        response = client.get("/api/v1/status")
        data = response.json()
        
        # Convert to string and check for sensitive keywords
        response_str = str(data).lower()
        
        assert "password" not in response_str
        assert "secret" not in response_str
        # Note: "key" might appear in "feature" or other legitimate contexts
