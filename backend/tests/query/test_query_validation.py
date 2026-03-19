"""
Unit and integration tests for query validation endpoint.

Tests request validation, error handling, and structured error responses
for the POST /api/v1/query endpoint.
"""

import sys
import os

# Add backend to path to import services - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from main import app
from schemas.router import RouterErrorCode
from api.v1.query import map_validation_error_to_router_error


# Note: client fixture is provided by tests/conftest.py


class TestQueryValidationEndpoint:
    """Integration tests for POST /api/v1/query endpoint validation."""
    
    @pytest.mark.asyncio
    async def test_valid_request_with_conversation_id(self, client):
        """Test valid request with an existing conversation ID."""
        # First create a conversation
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Initial query"},
        )
        assert response1.status_code == 200
        conv_id = response1.json()["conversation_id"]
        
        # Mark as COMPLETE so a new turn can start
        from services.conversation_state import conversation_state_manager
        from schemas.conversation import ConversationStatus
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)
        
        # Now send a follow-up with the conversation_id
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show me sales from last month",
                "conversation_id": conv_id,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conversation_id"] == conv_id
        assert data["query"] == "Show me sales from last month"
        assert "timestamp" in data
        assert "correlation_id" in data
    
    @pytest.mark.asyncio
    async def test_valid_request_without_conversation_id(self, client):
        """Test valid request without conversation ID (will be generated)."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "How many active users do we have?"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conversation_id"] is not None  # Should be generated
        assert data["query"] == "How many active users do we have?"
    
    @pytest.mark.asyncio
    async def test_valid_request_with_whitespace_stripped(self, client):
        """Test that leading/trailing whitespace is stripped from query."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "  Show me revenue  \n\t"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "Show me revenue"
    
    @pytest.mark.asyncio
    async def test_empty_query_rejected(self, client):
        """Test that empty query is rejected with appropriate error."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": ""
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == RouterErrorCode.QUERY_EMPTY.value
    
    @pytest.mark.asyncio
    async def test_whitespace_only_query_rejected(self, client):
        """Test that whitespace-only query is rejected."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "   \n\t   "
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.QUERY_EMPTY.value
    
    @pytest.mark.asyncio
    async def test_query_too_long_rejected(self, client):
        """Test that query exceeding max length is rejected."""
        long_query = "a" * 10001  # MAX_QUERY_LENGTH is 10000
        
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": long_query
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.QUERY_TOO_LONG.value
    
    @pytest.mark.asyncio
    async def test_query_at_max_length_accepted(self, client):
        """Test that query at exactly max length is accepted."""
        max_length_query = "a" * 10000
        
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": max_length_query
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["query"]) == 10000
    
    @pytest.mark.asyncio
    async def test_query_with_null_byte_rejected(self, client):
        """Test that query with null byte is rejected."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "test\x00query"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == RouterErrorCode.INVALID_QUERY.value
    
    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format_rejected(self, client):
        """Test that invalid UUID format is rejected."""
        invalid_ids = [
            "not-a-uuid",
            "12345678-1234-1234-1234-123456789012",  # Not v4
            "g1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",  # Invalid hex
        ]
        
        for invalid_id in invalid_ids:
            response = await client.post(
                "/api/v1/query/start",
                json={
                    "query": "test query",
                    "conversation_id": invalid_id
                }
            )
            
            assert response.status_code == 400
            data = response.json()
            assert data["error_code"] == RouterErrorCode.INVALID_CONVERSATION_ID.value
    
    @pytest.mark.asyncio
    async def test_missing_query_field_rejected(self, client):
        """Test that request without query field is rejected."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
            }
        )
        
        assert response.status_code == 422  # Unprocessable Entity from FastAPI
    
    @pytest.mark.asyncio
    async def test_malformed_json_rejected(self, client):
        """Test that malformed JSON is rejected."""
        response = await client.post(
            "/api/v1/query/start",
            content=b"{ invalid json }",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_wrong_content_type_rejected(self, client):
        """Test that non-JSON content type is rejected."""
        response = await client.post(
            "/api/v1/query/start",
            content=b"query=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_null_query_rejected(self, client):
        """Test that null query value is rejected."""
        response = await client.post(
            "/api/v1/query/start",
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
    
    @pytest.mark.asyncio
    async def test_conversation_id_case_insensitive(self, client):
        """Test that conversation ID is case-insensitive and normalized."""
        # First create a conversation
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Initial query"},
        )
        assert response1.status_code == 200
        conv_id = response1.json()["conversation_id"]
        
        # Mark as COMPLETE so a new turn can start
        from services.conversation_state import conversation_state_manager
        from schemas.conversation import ConversationStatus
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)
        
        # Send the uppercase version
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "test query",
                "conversation_id": conv_id.upper(),
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should be normalized to lowercase
        assert data["conversation_id"] == conv_id.lower()
    
    @pytest.mark.asyncio
    async def test_correlation_id_included_in_response(self, client):
        """Test that correlation ID is included in response if provided."""
        correlation_id = "test-correlation-123"
        
        response = await client.post(
            "/api/v1/query/start",
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
    
    @pytest.mark.asyncio
    async def test_unicode_characters_in_query(self, client):
        """Test that unicode characters are accepted."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show me データ for 用户 with émojis 🎉"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "データ" in data["query"]
        assert "🎉" in data["query"]
    
    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, client):
        """Test that special SQL characters are accepted (not filtered)."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "SELECT * FROM users WHERE name = 'O''Neill'"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "O''Neill" in data["query"]
    
    @pytest.mark.asyncio
    async def test_newlines_in_query(self, client):
        """Test that newlines in query are accepted."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show me sales\nfrom last month\nfor region 'North'"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "\n" in data["query"]
    
    @pytest.mark.asyncio
    async def test_empty_user_context_accepted(self, client):
        """Test that empty user context is accepted."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "test",
                "user_context": {}
            }
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_partial_user_context_accepted(self, client):
        """Test that partial user context is accepted."""
        response = await client.post(
            "/api/v1/query/start",
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
    
    @pytest.mark.asyncio
    async def test_openapi_schema_includes_query_endpoint(self, client):
        """Test that OpenAPI schema includes the query endpoint."""
        response = await client.get("/openapi.json")
        
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/query/start" in schema["paths"]
    
    @pytest.mark.asyncio
    async def test_query_endpoint_has_proper_documentation(self, client):
        """Test that query endpoint has proper OpenAPI documentation."""
        response = await client.get("/openapi.json")
        schema = response.json()
        
        query_endpoint = schema["paths"]["/api/v1/query/start"]["post"]
        assert "summary" in query_endpoint
        assert "description" in query_endpoint
        assert "requestBody" in query_endpoint
        assert "responses" in query_endpoint
        
        # Check response schemas
        responses = query_endpoint["responses"]
        assert "200" in responses  # Success
        assert "400" in responses  # Validation error
        assert "422" in responses  # Unprocessable entity
