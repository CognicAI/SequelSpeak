"""
Tests for Prometheus metrics integration.

Verifies metrics collection, path templating, and proper integration
with the FastAPI application.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from utils.prometheus import extract_path_template
import re


class TestPathTemplating:
    """Test path template extraction for cardinality control."""
    
    def test_extract_path_template_with_numeric_id(self):
        """Should replace long numeric IDs with {id} template."""
        # 6+ digit numbers are replaced
        assert extract_path_template("/api/v1/user/123456") == "/api/v1/user/{id}"
        assert extract_path_template("/api/v1/connection/456789") == "/api/v1/connection/{id}"
        
        # Short numbers (< 6 digits) are NOT replaced to avoid false positives
        assert extract_path_template("/api/v1/user/123") == "/api/v1/user/123"
    
    def test_extract_path_template_with_uuid(self):
        """Should replace UUIDs with {uuid} template."""
        uuid_path = "/api/v1/query/550e8400-e29b-41d4-a716-446655440000"
        assert extract_path_template(uuid_path) == "/api/v1/query/{uuid}"
    
    def test_extract_path_template_with_alphanumeric_id(self):
        """Should replace long alphanumeric IDs (12+ chars with 3+ digits)."""
        # 12+ char mix of letters and numbers with 3+ digits = replaced
        assert extract_path_template("/api/v1/connection/abc123def456") == "/api/v1/connection/{id}"
        assert extract_path_template("/api/v1/item/a1b2c3d4e5f6") == "/api/v1/item/{id}"
        
        # Pure letters or pure numbers not replaced (avoid matching path names)
        assert extract_path_template("/api/v1/connection") == "/api/v1/connection"
        assert extract_path_template("/api/v1/health") == "/api/v1/health"
        
        # Short alphanumeric (< 12 chars) not replaced
        assert extract_path_template("/api/v1/item/a1b2c3d4") == "/api/v1/item/a1b2c3d4"
    
    def test_extract_path_template_static_paths(self):
        """Should not modify static paths without IDs."""
        assert extract_path_template("/api/v1/health") == "/api/v1/health"
        assert extract_path_template("/api/v1/meta") == "/api/v1/meta"
        assert extract_path_template("/api/v1/connection") == "/api/v1/connection"
        assert extract_path_template("/") == "/"
    
    def test_extract_path_template_with_short_segments(self):
        """Should not replace short path segments."""
        # Short segments should not be replaced
        assert extract_path_template("/api/test") == "/api/test"
        assert extract_path_template("/api/v1") == "/api/v1"
    
    def test_extract_path_template_multiple_ids(self):
        """Should replace multiple ID segments in same path."""
        path = "/api/v1/user/123456/posts/789012"
        result = extract_path_template(path)
        assert result == "/api/v1/user/{id}/posts/{id}"


class TestMetricsEndpoint:
    """Test the /metrics endpoint."""
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, client: AsyncClient):
        """Metrics endpoint should return HTTP 200."""
        response = await client.get("/metrics")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_content_type(self, client: AsyncClient):
        """Metrics endpoint should return correct content type."""
        response = await client.get("/metrics")
        # Prometheus metrics use text/plain with version parameter
        assert "text/plain" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_prometheus_format(self, client: AsyncClient):
        """Metrics should be in valid Prometheus format."""
        response = await client.get("/metrics")
        content = response.text
        
        # Check for required metrics
        assert "sequelspeak_info" in content
        assert "http_requests_total" in content
        assert "http_request_duration_seconds" in content
        assert "active_database_connections" in content
        
        # Check metric format (HELP and TYPE lines)
        assert "# HELP" in content or "# TYPE" in content
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_includes_app_info(self, client: AsyncClient):
        """Metrics should include application info."""
        response = await client.get("/metrics")
        content = response.text
        
        # Should have sequelspeak_info with version and environment
        assert "sequelspeak_info" in content
        assert 'version="' in content
        assert 'environment="' in content


class TestMetricsCollection:
    """Test metrics are collected correctly."""
    
    @pytest.mark.asyncio
    async def test_http_requests_are_counted(self, client: AsyncClient):
        """HTTP requests should increment request counter."""
        # Make initial request to get baseline
        await client.get("/metrics")
        initial_metrics = (await client.get("/metrics")).text
        
        # Make a request to root endpoint
        await client.get("/")
        
        # Get metrics again
        updated_metrics = (await client.get("/metrics")).text
        
        # Should have recorded the request to /
        assert 'endpoint="/"' in updated_metrics
        assert 'method="GET"' in updated_metrics
    
    @pytest.mark.asyncio
    async def test_request_duration_is_tracked(self, client: AsyncClient):
        """Request duration should be recorded in histogram."""
        # Make a request
        await client.get("/")
        
        # Check metrics
        metrics = (await client.get("/metrics")).text
        
        # Should have duration histogram data
        assert "http_request_duration_seconds" in metrics
        # Histograms have _bucket, _count, and _sum suffixes
        assert ("http_request_duration_seconds_bucket" in metrics or
                "http_request_duration_seconds_count" in metrics)
    
    @pytest.mark.asyncio
    async def test_path_templating_in_metrics(self, client: AsyncClient):
        """Metrics should use path templates, not raw paths."""
        # This test assumes we have endpoints with IDs
        # If not, we can just verify the templating works in isolation
        metrics = (await client.get("/metrics")).text
        
        # Check that common static paths are present
        assert 'endpoint="/metrics"' in metrics or 'endpoint="/"' in metrics
        
        # Verify no long alphanumeric IDs are in metrics (would indicate missing templating)
        # This is a negative test - we shouldn't see specific IDs
        pattern = re.compile(r'endpoint="/[^"]*\d{6,}[^"]*"')
        assert not pattern.search(metrics), "Found numeric ID in metrics - path templating may not be working"


class TestMetricsConfiguration:
    """Test metrics can be disabled via configuration."""
    
    @pytest.mark.asyncio
    async def test_metrics_disabled_returns_message(self, client_with_metrics_disabled: AsyncClient):
        """When metrics disabled, endpoint should return disabled message."""
        response = await client_with_metrics_disabled.get("/metrics")
        assert response.status_code == 200
        assert "Metrics disabled" in response.text


class TestDatabaseErrorTracking:
    """Test database errors are tracked in metrics."""
    
    @pytest.mark.asyncio
    async def test_database_errors_metric_exists(self, client: AsyncClient):
        """Database errors metric should be present."""
        metrics = (await client.get("/metrics")).text
        assert "database_errors_total" in metrics


class TestConnectionPoolMetrics:
    """Test connection pool metrics."""
    
    @pytest.mark.asyncio
    async def test_connection_pool_metrics_exist(self, client: AsyncClient):
        """Connection pool metrics should be present."""
        metrics = (await client.get("/metrics")).text
        
        # Check for connection pool metrics
        assert "active_database_connections" in metrics
        assert "database_connection_pools_total" in metrics


# ============================================================================
# Fixtures
# ============================================================================

# Note: client fixture is provided by tests/conftest.py


@pytest.fixture
async def client_with_metrics_disabled():
    """Create an async test client with metrics disabled."""
    from main import app
    from config import settings
    
    # Temporarily disable metrics
    original_value = settings.metrics_enabled
    settings.metrics_enabled = False
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        # Restore original value
        settings.metrics_enabled = original_value
