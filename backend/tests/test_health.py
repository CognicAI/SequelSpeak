"""
Tests for health check endpoint.

Tests cover:
- Health endpoint response structure
- Database connectivity status reporting
- Latency measurement
- Graceful failure handling
- No credential exposure
"""

import sys
import os
import time
from fastapi.testclient import TestClient

# Add backend to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from config import settings


client = TestClient(app)


# ============================================================================
# RESPONSE STRUCTURE TESTS
# ============================================================================

class TestHealthEndpointStructure:
    """Tests for health endpoint response structure."""

    def test_health_endpoint_exists(self):
        """Test that /api/v1/health endpoint exists and responds."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_has_required_fields(self):
        """Test that response contains all required fields."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
        assert "status" in data["database"]

    def test_health_status_is_always_ok(self):
        """Test that API status is always 'ok' when endpoint responds."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        assert data["status"] == "ok"

    def test_health_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO 8601 format."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # ISO 8601 format check - should contain 'T' separator
        assert "T" in data["timestamp"]


# ============================================================================
# DATABASE STATUS TESTS
# ============================================================================

class TestDatabaseHealthStatus:
    """Tests for database health reporting."""

    def test_database_status_reporting(self):
        """Test health check reports database status (connected/unavailable/unknown)."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert response.status_code == 200
        assert data["database"]["status"] in ["connected", "unavailable", "unknown"]
        assert "consecutive_failures" in data["database"]

    def test_database_status_with_configured_url(self):
        """Test health check when database URL is configured."""
        if not settings.health_check_db_url:
            # If no URL configured, status should be unknown
            response = client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["status"] == "unknown"
            assert data["database"]["latency_ms"] is None
        else:
            # If URL is configured, check for connected or unavailable
            response = client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["status"] in ["connected", "unavailable"]
            assert isinstance(data["database"]["consecutive_failures"], int)


# ============================================================================
# LATENCY TESTS
# ============================================================================

class TestHealthLatency:
    """Tests for response latency measurement."""

    def test_latency_is_measured_when_db_configured(self):
        """Test that latency_ms is populated when database URL is configured."""
        if not settings.health_check_db_url:
            # Skip if no URL configured
            response = client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["latency_ms"] is None
        else:
            response = client.get("/api/v1/health")
            data = response.json()
            
            # Latency should be measured regardless of success/failure
            if data["database"]["status"] in ["connected", "unavailable"]:
                assert data["database"]["latency_ms"] is not None
                assert isinstance(data["database"]["latency_ms"], int)
                assert data["database"]["latency_ms"] >= 0

    def test_endpoint_response_time(self):
        """Test that health endpoint responds quickly."""
        start = time.perf_counter()
        response = client.get("/api/v1/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        # Health endpoint should respond within 5 seconds (includes DB timeout)
        assert elapsed_ms < 5000, f"Response took {elapsed_ms}ms, expected <5000ms"


# ============================================================================
# GRACEFUL FAILURE TESTS
# ============================================================================

class TestGracefulFailure:
    """Tests for graceful failure handling."""

    def test_always_returns_200(self):
        """Test that endpoint always returns 200 regardless of database state."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_response_structure_on_any_state(self):
        """Test that response always has proper structure."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # Should always have these fields
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
        assert data["status"] == "ok"


# ============================================================================
# SECURITY TESTS
# ============================================================================

class TestNoCredentialExposure:
    """Tests to ensure credentials are never exposed in health response."""

    def test_no_credentials_in_response(self):
        """Test that database credentials are not exposed in response."""
        response = client.get("/api/v1/health")
        response_text = response.text.lower()
        
        # Check for common credential patterns (if URL is configured)
        if settings.health_check_db_url:
            # Response should not contain the actual password or full URL
            assert "password" not in response_text or "null" in response_text
            assert "postgres://" not in response_text
            
    def test_response_only_has_safe_fields(self):
        """Test that response only contains expected safe fields."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # Verify only expected keys exist
        assert set(data.keys()) == {"status", "timestamp", "database"}
        assert set(data["database"].keys()) == {"status", "latency_ms", "consecutive_failures"}

    def test_no_sensitive_data_in_headers(self):
        """Test that response headers don't leak sensitive information."""
        response = client.get("/api/v1/health")
        
        # Check headers don't contain sensitive data
        headers_str = str(response.headers).lower()
        assert "password" not in headers_str
        assert "secret" not in headers_str


# ============================================================================
# COMPREHENSIVE INTEGRATION TESTS
# ============================================================================

class TestHealthEndpointIntegration:
    """Comprehensive integration tests for all system states."""

    def test_health_endpoint_complete_flow(self):
        """
        INTEGRATION TEST: Complete health check flow
        - Endpoint is accessible
        - Returns proper structure
        - No credentials exposed
        """
        response = client.get("/api/v1/health")
        data = response.json()
        
        # Status checks
        assert response.status_code == 200
        assert data["status"] == "ok"
        assert data["database"]["status"] in ["connected", "unavailable", "unknown"]
        
        # Structure validation
        assert "timestamp" in data
        assert "T" in data["timestamp"]
        
        # Database field validation
        assert "status" in data["database"]
        assert "latency_ms" in data["database"]
        assert "consecutive_failures" in data["database"]
        
        # Type validation
        if data["database"]["latency_ms"] is not None:
            assert isinstance(data["database"]["latency_ms"], int)
            assert data["database"]["latency_ms"] >= 0
        assert isinstance(data["database"]["consecutive_failures"], int)
        
        # Security validation - no credentials in response
        assert "password" not in response.text.lower() or "null" in response.text.lower()

    def test_health_check_idempotency(self):
        """
        Test that multiple calls return consistent structure.
        """
        response1 = client.get("/api/v1/health")
        response2 = client.get("/api/v1/health")
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Both should return 200
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Both should have same structure
        assert set(data1.keys()) == set(data2.keys())
        assert set(data1["database"].keys()) == set(data2["database"].keys())
        
        # Database status should be stable (same state)
        # Note: This might differ if DB state changes between calls
        assert data1["database"]["status"] in ["connected", "unavailable", "unknown"]
        assert data2["database"]["status"] in ["connected", "unavailable", "unknown"]
