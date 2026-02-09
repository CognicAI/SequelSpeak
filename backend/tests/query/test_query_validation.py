"""
Unit and integration tests for query validation endpoint.

Tests request validation, error handling, and structured error responses
for the POST /api/v1/query endpoint.
"""

import sys
import os

# Add backend to path to import services - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from schemas.router import RouterErrorCode
from api.v1.query import map_validation_error_to_router_error

# Create test client
client = TestClient(app)


class TestQueryValidationEndpoint:
    """Integration tests for POST /api/v1/query endpoint validation."""
    
    def test_valid_request_with_conversation_id(self):
        """Test valid request with conversation ID."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "Show me sales from last month",
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conversation_id"] == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        assert data["query"] == "Show me sales from last month"
        assert "timestamp" in data
        assert "correlation_id" in data
    
    def test_valid_request_without_conversation_id(self):
        """Test valid request without conversation ID (will be generated)."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "How many active users do we have?"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conversation_id"] is not None  # Should be generated
        assert data["query"] == "How many active users do we have?"
    
    def test_valid_request_with_whitespace_stripped(self):
        """Test that leading/trailing whitespace is stripped from query."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "  Show me revenue  \n\t"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "Show me revenue"
    
    def test_empty_query_rejected(self):
        """Test that empty query is rejected with appropriate error."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": ""
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == RouterErrorCode.QUERY_EMPTY.value
    
    def test_whitespace_only_query_rejected(self):
        """Test that whitespace-only query is rejected."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "   \n\t   "
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.QUERY_EMPTY.value
    
    def test_query_too_long_rejected(self):
        """Test that query exceeding max length is rejected."""
        long_query = "a" * 10001  # MAX_QUERY_LENGTH is 10000
        
        response = client.post(
            "/api/v1/query",
            json={
                "query": long_query
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.QUERY_TOO_LONG.value
    
    def test_query_at_max_length_accepted(self):
        """Test that query at exactly max length is accepted."""
        max_length_query = "a" * 10000
        
        response = client.post(
            "/api/v1/query",
            json={
                "query": max_length_query
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["query"]) == 10000
    
    def test_query_with_null_byte_rejected(self):
        """Test that query with null byte is rejected."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "test\x00query"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.INVALID_QUERY.value
    
    def test_invalid_conversation_id_format_rejected(self):
        """Test that invalid UUID format is rejected."""
        invalid_ids = [
            "not-a-uuid",
            "12345678-1234-1234-1234-123456789012",  # Not v4
            "g1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",  # Invalid hex
        ]
        
        for invalid_id in invalid_ids:
            response = client.post(
                "/api/v1/query",
                json={
                    "query": "test query",
                    "conversation_id": invalid_id
                }
            )
            
            assert response.status_code == 400
            data = response.json()
            assert data["error_code"] == RouterErrorCode.INVALID_CONVERSATION_ID.value
    
    def test_missing_query_field_rejected(self):
        """Test that request without query field is rejected."""
        response = client.post(
            "/api/v1/query",
            json={
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
            }
        )
        
        assert response.status_code == 422  # Unprocessable Entity from FastAPI
    
    def test_malformed_json_rejected(self):
        """Test that malformed JSON is rejected."""
        response = client.post(
            "/api/v1/query",
            content=b"{ invalid json }",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
    
    def test_wrong_content_type_rejected(self):
        """Test that non-JSON content type is rejected."""
        response = client.post(
            "/api/v1/query",
            content=b"query=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 422
    
    def test_null_query_rejected(self):
        """Test that null query value is rejected."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": None
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] in [
            RouterErrorCode.QUERY_EMPTY.value,
            RouterErrorCode.INVALID_QUERY.value
        ]
    
    def test_conversation_id_case_insensitive(self):
        """Test that conversation ID is case-insensitive and normalized."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "test query",
                "conversation_id": "A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should be normalized to lowercase
        assert data["conversation_id"] == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    
    def test_correlation_id_included_in_response(self):
        """Test that correlation ID is included in response if provided."""
        correlation_id = "test-correlation-123"
        
        response = client.post(
            "/api/v1/query",
            json={"query": "test"},
            headers={"X-Correlation-ID": correlation_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["correlation_id"] == correlation_id


class TestValidationErrorMapping:
    """Unit tests for validation error mapping logic."""
    
    def test_map_query_too_long_error(self):
        """Test mapping of query too long error."""
        # Create a mock ValidationError for query too long
        try:
            from schemas.router import RouterRequest
            RouterRequest(query="a" * 10001)
        except ValidationError as e:
            error_code, error_message = map_validation_error_to_router_error(e)
            assert error_code == RouterErrorCode.QUERY_TOO_LONG
            assert "length" in error_message.lower() or "long" in error_message.lower()
    
    def test_map_query_empty_error(self):
        """Test mapping of empty query error."""
        try:
            from schemas.router import RouterRequest
            RouterRequest(query="")
        except ValidationError as e:
            error_code, error_message = map_validation_error_to_router_error(e)
            assert error_code == RouterErrorCode.QUERY_EMPTY
            assert error_message  # Verify message is returned
    
    def test_map_invalid_conversation_id_error(self):
        """Test mapping of invalid conversation ID error."""
        try:
            from schemas.router import RouterRequest
            RouterRequest(query="test", conversation_id="not-a-uuid")
        except ValidationError as e:
            error_code, message = map_validation_error_to_router_error(e)
            assert error_code == RouterErrorCode.INVALID_CONVERSATION_ID
            assert "uuid" in message.lower() or "format" in message.lower()
    
    def test_map_generic_validation_error(self):
        """Test mapping of generic validation error."""
        try:
            from schemas.router import RouterRequest
            # Force a type error by passing invalid type
            RouterRequest(query=123)  # type: ignore
        except ValidationError as e:
            error_code, error_message = map_validation_error_to_router_error(e)
            assert error_code in [
                RouterErrorCode.INVALID_QUERY,
                RouterErrorCode.INVALID_REQUEST
            ]
            assert error_message  # Verify message is returned


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_unicode_characters_in_query(self):
        """Test that unicode characters are accepted."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "Show me データ for 用户 with émojis 🎉"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "データ" in data["query"]
        assert "🎉" in data["query"]
    
    def test_special_characters_in_query(self):
        """Test that special SQL characters are accepted (not filtered)."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "SELECT * FROM users WHERE name = 'O''Neill'"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "O''Neill" in data["query"]
    
    def test_newlines_in_query(self):
        """Test that newlines in query are accepted."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "Show me sales\nfrom last month\nfor region 'North'"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "\n" in data["query"]
    
    def test_empty_user_context_accepted(self):
        """Test that empty user context is accepted."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "test",
                "user_context": {}
            }
        )
        
        assert response.status_code == 200
    
    def test_partial_user_context_accepted(self):
        """Test that partial user context is accepted."""
        response = client.post(
            "/api/v1/query",
            json={
                "query": "test",
                "user_context": {
                    "user_id": "user123"
                }
            }
        )
        
        assert response.status_code == 200


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation generation."""
    
    def test_openapi_schema_includes_query_endpoint(self):
        """Test that OpenAPI schema includes the query endpoint."""
        response = client.get("/openapi.json")
        
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/query" in schema["paths"]
    
    def test_query_endpoint_has_proper_documentation(self):
        """Test that query endpoint has proper OpenAPI documentation."""
        response = client.get("/openapi.json")
        schema = response.json()
        
        query_endpoint = schema["paths"]["/api/v1/query"]["post"]
        assert "summary" in query_endpoint
        assert "description" in query_endpoint
        assert "requestBody" in query_endpoint
        assert "responses" in query_endpoint
        
        # Check response schemas
        responses = query_endpoint["responses"]
        assert "200" in responses  # Success
        assert "400" in responses  # Validation error
        assert "422" in responses  # Unprocessable entity
