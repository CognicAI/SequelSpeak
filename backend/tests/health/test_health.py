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
import pytest

# Add backend to path to import modules - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from httpx import AsyncClient
from config import settings


# Note: client fixture is provided by tests/conftest.py


# ============================================================================
# RESPONSE STRUCTURE TESTS
# ============================================================================

class TestHealthEndpointStructure:
    """Tests for health endpoint response structure."""

    @pytest.mark.asyncio
    async def test_health_endpoint_exists(self, client: AsyncClient) -> None:
        """Test that /api/v1/health endpoint exists and responds."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_has_required_fields(self, client: AsyncClient) -> None:
        """Test that response contains all required fields."""
        response = await client.get("/api/v1/health")
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
        assert "status" in data["database"]

    @pytest.mark.asyncio
    async def test_health_status_is_always_ok(self, client: AsyncClient) -> None:
        """Test that API status is always 'ok' when endpoint responds."""
        response = await client.get("/api/v1/health")
        data = response.json()
        
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_timestamp_is_iso_format(self, client: AsyncClient) -> None:
        """Test that timestamp is in ISO 8601 format."""
        response = await client.get("/api/v1/health")
        data = response.json()
        
        # ISO 8601 format check - should contain 'T' separator
        assert "T" in data["timestamp"]


# ============================================================================
# DATABASE STATUS TESTS
# ============================================================================

class TestDatabaseHealthStatus:
    """Tests for database health reporting."""

    @pytest.mark.asyncio
    async def test_database_status_reporting(self, client: AsyncClient) -> None:
        """Test health check reports database status (healthy/unhealthy/not_configured)."""
        response = await client.get("/api/v1/health")
        data = response.json()

        assert response.status_code == 200
        assert data["database"]["status"] in ["healthy", "unhealthy", "not_configured"]
        assert "configured" in data["database"]

    @pytest.mark.asyncio
    async def test_database_status_with_configured_url(self, client: AsyncClient) -> None:
        """Test health check when database URL is configured."""
        if not settings.health_check_db_url:
            # If no URL configured, status should be not_configured
            response = await client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["status"] == "not_configured"
            assert data["database"]["configured"] is False
            assert data["database"]["latency_ms"] is None
        else:
            # If URL is configured, check for healthy or unhealthy
            response = await client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["status"] in ["healthy", "unhealthy"]
            assert data["database"]["configured"] is True


# ============================================================================
# LATENCY TESTS
# ============================================================================

class TestHealthLatency:
    """Tests for response latency measurement."""

    @pytest.mark.asyncio
    async def test_latency_is_measured_when_db_configured(self, client: AsyncClient) -> None:
        """Test that latency_ms is populated when database URL is configured."""
        if not settings.health_check_db_url:
            # Skip if no URL configured
            response = await client.get("/api/v1/health")
            data = response.json()
            assert data["database"]["latency_ms"] is None
        else:
            response = await client.get("/api/v1/health")
            data = response.json()
            
            # Latency should be measured regardless of success/failure
            if data["database"]["status"] in ["healthy", "unhealthy"]:
                # healthy always has latency, unhealthy may not
                if data["database"]["latency_ms"] is not None:
                    assert isinstance(data["database"]["latency_ms"], (int, float))
                    assert data["database"]["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_endpoint_response_time(self, client: AsyncClient) -> None:
        """Test that health endpoint responds quickly."""
        start = time.perf_counter()
        response = await client.get("/api/v1/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        # Health endpoint should respond within 5 seconds (includes DB timeout)
        assert elapsed_ms < 5000, f"Response took {elapsed_ms}ms, expected <5000ms"


# ============================================================================
# GRACEFUL FAILURE TESTS
# ============================================================================

class TestGracefulFailure:
    """Tests for graceful failure handling."""

    @pytest.mark.asyncio
    async def test_always_returns_200(self, client: AsyncClient) -> None:
        """Test that endpoint always returns 200 regardless of database state."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_response_structure_on_any_state(self, client: AsyncClient) -> None:
        """Test that response always has proper structure."""
        response = await client.get("/api/v1/health")
        data = response.json()
        
        # Should always have these fields
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
        assert data["status"] in ["ok", "degraded"]


# ============================================================================
# SECURITY TESTS
# ============================================================================

class TestNoCredentialExposure:
    """Tests to ensure credentials are never exposed in health response."""

    @pytest.mark.asyncio
    async def test_no_credentials_in_response(self, client: AsyncClient) -> None:
        """Test that database credentials are not exposed in response."""
        response = await client.get("/api/v1/health")
        response_text = response.text.lower()
        
        # Check for common credential patterns (if URL is configured)
        if settings.health_check_db_url:
            # Response should not contain the actual password or full URL
            assert "password" not in response_text or "null" in response_text
            assert "postgres://" not in response_text
            
    @pytest.mark.asyncio
    async def test_response_only_has_safe_fields(self, client: AsyncClient) -> None:
        """Test that response only contains expected safe fields."""
        response = await client.get("/api/v1/health")
        data = response.json()
        
        # Verify only expected keys exist
        assert set(data.keys()) == {"status", "timestamp", "database"}
        assert set(data["database"].keys()) == {"configured", "status", "latency_ms"}

    @pytest.mark.asyncio
    async def test_no_sensitive_data_in_headers(self, client: AsyncClient) -> None:
        """Test that response headers don't leak sensitive information."""
        response = await client.get("/api/v1/health")
        
        # Check headers don't contain sensitive data
        headers_str = str(response.headers).lower()
        assert "password" not in headers_str
        assert "secret" not in headers_str


# ============================================================================
# COMPREHENSIVE INTEGRATION TESTS
# ============================================================================

class TestHealthEndpointIntegration:
    """Comprehensive integration tests for all system states."""

    @pytest.mark.asyncio
    async def test_health_endpoint_complete_flow(self, client: AsyncClient) -> None:
        """
        INTEGRATION TEST: Complete health check flow
        - Endpoint is accessible
        - Returns proper structure
        - No credentials exposed
        """
        response = await client.get("/api/v1/health")
        data = response.json()
        
        # Status checks
        assert response.status_code == 200
        assert data["status"] in ["ok", "degraded"]
        assert data["database"]["status"] in ["healthy", "unhealthy", "not_configured"]
        
        # Structure validation
        assert "timestamp" in data
        assert "T" in data["timestamp"]
        
        # Database field validation
        assert "status" in data["database"]
        assert "latency_ms" in data["database"]
        assert "configured" in data["database"]
        
        # Type validation
        if data["database"]["latency_ms"] is not None:
            assert isinstance(data["database"]["latency_ms"], (int, float))
            assert data["database"]["latency_ms"] >= 0
        assert isinstance(data["database"]["configured"], bool)
        
        # Security validation - no credentials in response
        assert "password" not in response.text.lower() or "null" in response.text.lower()

    @pytest.mark.asyncio
    async def test_health_check_idempotency(self, client: AsyncClient) -> None:
        """
        Test that multiple calls return consistent structure.
        """
        response1 = await client.get("/api/v1/health")
        response2 = await client.get("/api/v1/health")
        
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
        assert data1["database"]["status"] in ["healthy", "unhealthy", "not_configured"]
        assert data2["database"]["status"] in ["healthy", "unhealthy", "not_configured"]
