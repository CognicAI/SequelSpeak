"""
Unit tests for Router request/response schemas.

Tests schema validation, field constraints, and error handling
for the Router entry point input contract.
"""

import sys
import os
import pytest
from pydantic import ValidationError

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path to import services

from schemas.router import (
    RouterRequest,
    RouterInitResponse,
    RouterErrorResponse,
    RouterErrorCode,
    UserContext,
    MAX_QUERY_LENGTH,
    ROUTER_SCHEMA_VERSION,
)


class TestRouterRequestSchema:
    """Test suite for RouterRequest schema validation."""
    
    def test_valid_request_with_conversation_id(self):
        """Test valid request with all fields provided."""
        request = RouterRequest(
            query="Show me sales from last month",
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            user_context=UserContext(user_id="user123")
        )
        
        assert request.query == "Show me sales from last month"
        assert request.conversation_id == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        assert request.user_context is not None
        assert request.user_context.user_id == "user123"
    
    def test_valid_request_without_conversation_id(self):
        """Test valid request without conversation ID (will be generated)."""
        request = RouterRequest(
            query="How many active users do we have?"
        )
        
        assert request.query == "How many active users do we have?"
        assert request.conversation_id is None
        assert request.user_context is not None  # Default factory creates instance
    
    def test_valid_request_minimal(self):
        """Test valid request with only required fields."""
        request = RouterRequest(query="SELECT * FROM users")
        
        assert request.query == "SELECT * FROM users"
        assert request.conversation_id is None
    
    def test_query_whitespace_stripping(self):
        """Test that leading/trailing whitespace is stripped from query."""
        request = RouterRequest(
            query="  Show me revenue  \n\t"
        )
        
        assert request.query == "Show me revenue"
    
    def test_conversation_id_lowercase_normalization(self):
        """Test that conversation ID is normalized to lowercase."""
        request = RouterRequest(
            query="test query",
            conversation_id="A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D"
        )
        
        assert request.conversation_id == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    
    def test_conversation_id_empty_string_treated_as_none(self):
        """Test that empty string conversation_id is treated as None."""
        request = RouterRequest(
            query="test query",
            conversation_id=""
        )
        
        assert request.conversation_id is None
    
    def test_conversation_id_whitespace_treated_as_none(self):
        """Test that whitespace-only conversation_id is treated as None."""
        request = RouterRequest(
            query="test query",
            conversation_id="   \t\n  "
        )
        
        assert request.conversation_id is None


class TestRouterRequestValidationErrors:
    """Test suite for RouterRequest validation error cases."""
    
    def test_empty_query_fails(self):
        """Test that empty query string is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "query" in errors[0]["loc"]
        # Pydantic's min_length validation or our custom validator will catch this
        assert any(keyword in errors[0]["msg"].lower() 
                  for keyword in ["empty", "whitespace", "at least", "character"])
    
    def test_whitespace_only_query_fails(self):
        """Test that whitespace-only query is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="   \n\t   ")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "query" in errors[0]["loc"]
        assert "empty" in errors[0]["msg"].lower() or "whitespace" in errors[0]["msg"].lower()
    
    def test_none_query_fails(self):
        """Test that None query is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query=None)  # type: ignore[arg-type]
        
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        # Pydantic will reject None for required str field
    
    def test_query_too_long_fails(self):
        """Test that query exceeding max length is rejected."""
        long_query = "a" * (MAX_QUERY_LENGTH + 1)
        
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query=long_query)
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "query" in errors[0]["loc"]
        # Check for either Pydantic's built-in message or our custom validator
        assert any(keyword in errors[0]["msg"].lower() 
                  for keyword in ["length", "maximum", "long", "at most", "character"])
    
    def test_query_at_max_length_succeeds(self):
        """Test that query at exactly max length is accepted."""
        max_length_query = "a" * MAX_QUERY_LENGTH
        
        request = RouterRequest(query=max_length_query)
        assert len(request.query) == MAX_QUERY_LENGTH
    
    def test_query_with_null_byte_fails(self):
        """Test that query with null byte is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="test\x00query")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "query" in errors[0]["loc"]
        assert "null" in errors[0]["msg"].lower()
    
    def test_query_with_url_encoded_null_byte_fails(self):
        """Test that query with URL-encoded null byte is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="test%00query")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "query" in errors[0]["loc"]
        assert "null" in errors[0]["msg"].lower()
    
    def test_invalid_conversation_id_format_fails(self):
        """Test that invalid UUID format is rejected."""
        invalid_ids = [
            "not-a-uuid",
            "12345678-1234-1234-1234-123456789012",  # Not v4 (missing '4' in version position)
            "a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d",  # Version 5, not v4
            "g1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",  # Invalid hex character 'g'
            "a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d",      # Missing dashes
            "a1b2c3d4-e5f6-4a7b-8c9d",                # Too short
        ]
        
        for invalid_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                RouterRequest(
                    query="test query",
                    conversation_id=invalid_id
                )
            
            errors = exc_info.value.errors()
            assert len(errors) == 1
            assert "conversation_id" in errors[0]["loc"]
            assert "uuid" in errors[0]["msg"].lower() or "format" in errors[0]["msg"].lower()
    
    def test_valid_uuid_v4_formats(self):
        """Test that various valid UUID v4 formats are accepted."""
        valid_ids = [
            "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",  # Lowercase
            "A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D",  # Uppercase
            "12345678-90ab-4cde-8f01-234567890abc",  # Valid v4 (4 in version position)
            "00000000-0000-4000-8000-000000000000",  # Edge case: all zeros with v4 markers
        ]
        
        for valid_id in valid_ids:
            request = RouterRequest(
                query="test query",
                conversation_id=valid_id
            )
            # Should be normalized to lowercase
            assert request.conversation_id == valid_id.lower()


class TestUserContextSchema:
    """Test suite for UserContext schema."""
    
    def test_user_context_default_values(self):
        """Test that UserContext has correct default values."""
        context = UserContext()
        
        assert context.user_id is None
        assert context.session_id is None
        assert context.ip_address is None
    
    def test_user_context_with_values(self):
        """Test UserContext with provided values."""
        context = UserContext(
            user_id="user123",
            session_id="session456",
            ip_address="192.168.1.1"
        )
        
        assert context.user_id == "user123"
        assert context.session_id == "session456"
        assert context.ip_address == "192.168.1.1"
    
    def test_user_context_partial_values(self):
        """Test UserContext with only some values provided."""
        context = UserContext(user_id="user123")
        
        assert context.user_id == "user123"
        assert context.session_id is None
        assert context.ip_address is None


class TestRouterInitResponse:
    """Test suite for RouterInitResponse schema."""
    
    def test_valid_response(self):
        """Test valid RouterInitResponse creation."""
        response = RouterInitResponse(
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            query="Show me revenue",
            timestamp="2026-02-08T10:30:00Z",
            correlation_id="req-123",
        )
        
        assert response.status == "success"
        assert response.conversation_id == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        assert response.query == "Show me revenue"
        assert response.timestamp == "2026-02-08T10:30:00Z"
        assert response.correlation_id == "req-123"
        assert response.message == "Query initialized successfully"
    
    def test_response_with_custom_message(self):
        """Test response with custom success message."""
        response = RouterInitResponse(
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            query="test",
            timestamp="2026-02-08T10:30:00Z",
            message="Custom success message"
        )
        
        assert response.message == "Custom success message"
    
    def test_response_without_correlation_id(self):
        """Test response without correlation ID."""
        response = RouterInitResponse(
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            query="test",
            timestamp="2026-02-08T10:30:00Z"
        )
        
        assert response.correlation_id is None


class TestRouterErrorResponse:
    """Test suite for RouterErrorResponse schema."""
    
    def test_valid_error_response(self):
        """Test valid error response creation."""
        error = RouterErrorResponse(
            detail="Query cannot be empty",
            error_code=RouterErrorCode.QUERY_EMPTY
        )
        
        assert error.detail == "Query cannot be empty"
        assert error.error_code == RouterErrorCode.QUERY_EMPTY
    
    def test_all_error_codes(self):
        """Test that all error codes can be used in error response."""
        error_codes = [
            RouterErrorCode.INVALID_QUERY,
            RouterErrorCode.QUERY_TOO_LONG,
            RouterErrorCode.QUERY_EMPTY,
            RouterErrorCode.INVALID_CONVERSATION_ID,
            RouterErrorCode.INVALID_REQUEST,
        ]
        
        for code in error_codes:
            error = RouterErrorResponse(
                detail=f"Test error for {code.value}",
                error_code=code
            )
            assert error.error_code == code


class TestSchemaVersioning:
    """Test suite for schema versioning."""
    
    def test_schema_version_exists(self):
        """Test that schema version constant is defined."""
        assert ROUTER_SCHEMA_VERSION is not None
        assert isinstance(ROUTER_SCHEMA_VERSION, str)
    
    def test_schema_version_format(self):
        """Test that schema version follows semantic versioning."""
        # Should be in format X.Y.Z
        parts = ROUTER_SCHEMA_VERSION.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)


class TestSchemaIntegration:
    """Integration tests for schema usage patterns."""
    
    def test_request_to_response_flow(self):
        """Test typical flow from request to response."""
        # Create request
        request = RouterRequest(
            query="Show me sales",
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        )
        
        # Simulate processing and create response
        response = RouterInitResponse(
            conversation_id=request.conversation_id or "12345678-90ab-4cde-8f01-234567890abc",
            query=request.query,
            timestamp="2026-02-08T10:30:00Z"
        )
        
        assert response.conversation_id == request.conversation_id
        assert response.query == request.query
        assert response.status == "success"
    
    def test_request_without_id_to_response_with_generated_id(self):
        """Test flow where conversation ID is generated."""
        # Create request without conversation_id
        request = RouterRequest(query="Show me sales")
        
        assert request.conversation_id is None
        
        # Simulate ID generation and response (valid UUID v4)
        generated_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        response = RouterInitResponse(
            conversation_id=generated_id,
            query=request.query,
            timestamp="2026-02-08T10:30:00Z"
        )
        
        assert response.conversation_id == generated_id
    
    def test_json_serialization(self):
        """Test that schemas can be serialized to JSON."""
        request = RouterRequest(
            query="test",
            conversation_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        )
        
        # Test model_dump (Pydantic v2)
        request_dict = request.model_dump()
        assert "query" in request_dict
        assert "conversation_id" in request_dict
        assert "user_context" in request_dict
        
        # Test model_dump_json
        json_str = request.model_dump_json()
        assert isinstance(json_str, str)
        assert "test" in json_str
    
    def test_json_schema_generation(self):
        """Test that OpenAPI schema can be generated."""
        schema = RouterRequest.model_json_schema()
        
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "conversation_id" in schema["properties"]
        assert "user_context" in schema["properties"]
        
        # Check required fields
        assert "required" in schema
        assert "query" in schema["required"]
        assert "conversation_id" not in schema["required"]  # Optional
