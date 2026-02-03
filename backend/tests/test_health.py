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
from unittest.mock import patch
from fastapi.testclient import TestClient

# Add backend to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from schemas.errors import ConnectionResult, ErrorCode


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

    def test_database_connected_status(self):
        """Test health check with successful database connection."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2

            response = client.get("/api/v1/health")
            data = response.json()

            assert response.status_code == 200
            assert data["database"]["status"] == "connected"
            assert data["database"]["consecutive_failures"] == 0

    def test_database_unavailable_status(self):
        """Test health check with failed database connection."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=False,
                message="Connection failed",
                error_code=ErrorCode.HOST_UNREACHABLE
            )
            mock_monitor.consecutive_failures = 3
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2

            response = client.get("/api/v1/health")
            data = response.json()
            assert response.status_code == 200  # Always 200
            assert data["database"]["status"] == "unavailable"
            assert data["database"]["consecutive_failures"] == 3

    def test_database_unknown_without_url(self):
        """Test health check returns 'unknown' when no URL configured."""
        with patch('api.v1.health.settings') as mock_settings:
            mock_settings.health_check_db_url = None
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            # Without URL, status should be unknown
            assert response.status_code == 200
            assert data["database"]["status"] == "unknown"


# ============================================================================
# LATENCY TESTS
# ============================================================================

class TestHealthLatency:
    """Tests for response latency measurement."""

    def test_latency_is_measured(self):
        """Test that latency_ms is populated on successful check."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            assert data["database"]["latency_ms"] is not None
            assert isinstance(data["database"]["latency_ms"], int)
            assert data["database"]["latency_ms"] >= 0

    def test_latency_under_200ms_with_mock(self):
        """Test that response is fast (<200ms) with mocked database."""
        import time
        
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            start = time.perf_counter()
            response = client.get("/api/v1/health")
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            assert response.status_code == 200
            assert elapsed_ms < 200, f"Response took {elapsed_ms}ms, expected <200ms"


# ============================================================================
# GRACEFUL FAILURE TESTS
# ============================================================================

class TestGracefulFailure:
    """Tests for graceful failure handling."""

    def test_returns_200_on_db_failure(self):
        """Test that endpoint returns 200 even when database is down."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=False,
                message="Connection refused",
                error_code=ErrorCode.HOST_UNREACHABLE
            )
            mock_monitor.consecutive_failures = 5
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            
            assert response.status_code == 200

    def test_returns_200_on_unexpected_error(self):
        """Test that endpoint returns 200 on unexpected exceptions."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.side_effect = RuntimeError("Unexpected error")
            mock_monitor.consecutive_failures = 1
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["database"]["status"] == "unavailable"

    def test_no_crash_on_exception(self):
        """Test that health endpoint never crashes the application."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.side_effect = Exception("Total system failure")
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            # Should NOT raise an exception
            response = client.get("/api/v1/health")
            
            assert response.status_code == 200


# ============================================================================
# SECURITY TESTS
# ============================================================================

class TestNoCredentialExposure:
    """Tests to ensure credentials are never exposed in health response."""

    def test_no_url_in_response(self):
        """Test that database URL is not exposed in response."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://admin:supersecret@prod.db.com:5432/mydb"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            response_text = response.text
            
            assert "supersecret" not in response_text
            assert "admin" not in response_text
            assert "prod.db.com" not in response_text

    def test_no_credentials_on_failure(self):
        """Test that credentials are not exposed even on connection failure."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=False,
                message="Connection failed for postgres://user:secret@host/db",
                error_code=ErrorCode.AUTH_FAILED
            )
            mock_monitor.consecutive_failures = 1
            mock_settings.health_check_db_url = "postgres://user:secret@host:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            response_text = response.text
            
            # Message from ConnectionResult should not be exposed in health response
            assert "secret" not in response_text
            assert "postgres://" not in response_text

    def test_response_only_has_safe_fields(self):
        """Test that response only contains expected safe fields."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://test:test@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            # Verify only expected keys exist
            assert set(data.keys()) == {"status", "timestamp", "database"}
            assert set(data["database"].keys()) == {"status", "latency_ms", "consecutive_failures"}

    def test_no_sensitive_data_in_headers(self):
        """Test that response headers don't leak sensitive information."""
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection is healthy"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://admin:secret@db.com:5432/prod"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            
            # Check headers don't contain sensitive data
            headers_str = str(response.headers).lower()
            assert "secret" not in headers_str
            assert "admin" not in headers_str
            assert "db.com" not in headers_str


# ============================================================================
# COMPREHENSIVE INTEGRATION TESTS
# ============================================================================

class TestHealthEndpointIntegration:
    """Comprehensive integration tests for all system states."""

    def test_healthy_database_complete_flow(self):
        """
        SCENARIO: Healthy database state
        - Database is reachable
        - Latency is measured
        - Response structure is valid
        - No credentials exposed
        """
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=True,
                message="Connection successful"
            )
            mock_monitor.consecutive_failures = 0
            mock_settings.health_check_db_url = "postgres://user:pass@localhost:5432/db"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            # Status checks
            assert response.status_code == 200
            assert data["status"] == "ok"
            assert data["database"]["status"] == "connected"
            
            # Structure validation
            assert "timestamp" in data
            assert "T" in data["timestamp"]
            
            # Latency validation
            assert data["database"]["latency_ms"] is not None
            assert isinstance(data["database"]["latency_ms"], int)
            assert data["database"]["latency_ms"] >= 0
            
            # Failure tracking
            assert data["database"]["consecutive_failures"] == 0
            
            # Security validation
            assert "pass" not in response.text
            assert "user" not in response.text

    def test_database_down_complete_flow(self):
        """
        SCENARIO: Database is down/unreachable
        - Database connection fails
        - Endpoint still returns 200
        - Status shows unavailable
        - Consecutive failures tracked
        - No credentials exposed
        """
        with patch('api.v1.health.health_monitor') as mock_monitor, \
             patch('api.v1.health.settings') as mock_settings:
            mock_monitor.check_connection.return_value = ConnectionResult(
                success=False,
                message="Database connection refused",
                error_code=ErrorCode.HOST_UNREACHABLE
            )
            mock_monitor.consecutive_failures = 5
            mock_settings.health_check_db_url = "postgres://admin:secret@db.example.com:5432/prod"
            mock_settings.health_check_timeout = 2
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            # Graceful degradation - API still responds
            assert response.status_code == 200
            assert data["status"] == "ok"
            
            # Database status reflects failure
            assert data["database"]["status"] == "unavailable"
            
            # Failure tracking works
            assert data["database"]["consecutive_failures"] == 5
            
            # Latency still measured
            assert data["database"]["latency_ms"] is not None
            assert isinstance(data["database"]["latency_ms"], int)
            
            # Security - no credentials in response
            assert "secret" not in response.text
            assert "admin" not in response.text
            assert "db.example.com" not in response.text

    def test_no_database_url_configured(self):
        """
        SCENARIO: No database URL configured
        - HEALTH_CHECK_DB_URL not set
        - Returns unknown status
        - No errors thrown
        """
        with patch('api.v1.health.settings') as mock_settings:
            mock_settings.health_check_db_url = None
            
            response = client.get("/api/v1/health")
            data = response.json()
            
            assert response.status_code == 200
            assert data["status"] == "ok"
            assert data["database"]["status"] == "unknown"
            assert data["database"]["latency_ms"] is None
            assert data["database"]["consecutive_failures"] == 0
