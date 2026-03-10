"""
Unit tests for Router input validation — gap coverage.

Covers validation paths not exercised by test_router_schema.py or
test_query_validation.py:
- UserContext.safe_dict() filtering
- RouterInitResponse negative conversation_id validation
- RouterRequest edge cases (non-string types, boundary lengths, extra fields)
- map_validation_error_to_router_error branch coverage
- Endpoint-level validation edge cases
"""

import sys
import os
import pytest
from pydantic import ValidationError

# Add backend to path — MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from schemas.router import (
    RouterRequest,
    RouterInitResponse,
    RouterErrorResponse,
    RouterErrorCode,
    UserContext,
    MAX_QUERY_LENGTH,
    MIN_QUERY_LENGTH,
)
from api.v1.query import map_validation_error_to_router_error


# ---------------------------------------------------------------------------
# UserContext.safe_dict()
# ---------------------------------------------------------------------------

class TestUserContextSafeDict:
    """Tests for UserContext.safe_dict() — sensitive-field filtering."""

    def test_safe_dict_excludes_ip_address(self):
        """ip_address must be excluded from safe_dict output."""
        ctx = UserContext(
            user_id="user1",
            session_id="sess1",
            ip_address="10.0.0.1",
        )
        safe = ctx.safe_dict()

        assert "ip_address" not in safe
        assert safe["user_id"] == "user1"
        assert safe["session_id"] == "sess1"

    def test_safe_dict_includes_non_sensitive_fields(self):
        """user_id and session_id should always appear in safe_dict."""
        ctx = UserContext(user_id="u", session_id="s")
        safe = ctx.safe_dict()

        assert "user_id" in safe
        assert "session_id" in safe

    def test_safe_dict_all_none(self):
        """safe_dict works when every field is None."""
        ctx = UserContext()
        safe = ctx.safe_dict()

        assert safe["user_id"] is None
        assert safe["session_id"] is None
        assert "ip_address" not in safe

    def test_safe_dict_only_ip_address_set(self):
        """If only ip_address is provided, safe_dict returns no sensitive data."""
        ctx = UserContext(ip_address="192.168.1.1")
        safe = ctx.safe_dict()

        assert "ip_address" not in safe
        assert safe["user_id"] is None
        assert safe["session_id"] is None


# ---------------------------------------------------------------------------
# RouterInitResponse — conversation_id validator negatives
# ---------------------------------------------------------------------------

class TestRouterInitResponseValidation:
    """Negative validation tests for RouterInitResponse.conversation_id."""

    def test_invalid_uuid_raises_validation_error(self):
        """Non-UUID conversation_id on response must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RouterInitResponse(
                conversation_id="not-a-uuid",
                query="test",
                timestamp="2026-01-01T00:00:00Z",
            )

        errors = exc_info.value.errors()
        assert any("conversation_id" in str(e.get("loc", "")) for e in errors)

    def test_non_v4_uuid_raises_validation_error(self):
        """UUID v5 should be rejected by the response validator."""
        with pytest.raises(ValidationError):
            RouterInitResponse(
                conversation_id="a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d",
                query="test",
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_empty_string_conversation_id_raises(self):
        """Empty string conversation_id on response must raise."""
        with pytest.raises(ValidationError):
            RouterInitResponse(
                conversation_id="",
                query="test",
                timestamp="2026-01-01T00:00:00Z",
            )


# ---------------------------------------------------------------------------
# RouterRequest — edge cases
# ---------------------------------------------------------------------------

class TestRouterRequestEdgeCases:
    """Edge-case validation for RouterRequest schema."""

    @pytest.mark.parametrize("bad_value", [123, 45.6, True, ["a"], {"q": 1}])
    def test_non_string_query_types_rejected(self, bad_value):
        """Non-string types passed as query must raise ValidationError."""
        with pytest.raises(ValidationError):
            RouterRequest(query=bad_value)  # type: ignore[arg-type]

    def test_single_character_query_succeeds(self):
        """A single non-whitespace character meets MIN_QUERY_LENGTH."""
        req = RouterRequest(query="x")
        assert req.query == "x"
        assert len(req.query) == MIN_QUERY_LENGTH

    def test_internal_whitespace_preserved(self):
        """Whitespace inside the query body is preserved (only edges stripped)."""
        req = RouterRequest(query="  hello   world  ")
        assert req.query == "hello   world"

    def test_extra_unknown_fields_ignored(self):
        """Extra fields not in the schema should be silently ignored."""
        req = RouterRequest(
            query="test",
            unknown_field="surprise",  # type: ignore[call-arg]
        )
        assert req.query == "test"
        assert not hasattr(req, "unknown_field")

    def test_tab_only_query_rejected(self):
        """Tab-only query counts as whitespace-only and must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="\t\t\t")

        errors = exc_info.value.errors()
        assert any("query" in str(e.get("loc", "")) for e in errors)

    def test_url_encoded_null_mixed_case_rejected(self):
        """Percent-encoded null bytes in varied casing must be rejected."""
        for variant in ["%00", "%0000", "prefix%00suffix"]:
            with pytest.raises(ValidationError) as exc_info:
                RouterRequest(query=variant)

            errors = exc_info.value.errors()
            assert len(errors) == 1
            assert "null" in errors[0]["msg"].lower()

    def test_query_just_below_max_length(self):
        """Query of MAX_QUERY_LENGTH - 1 should succeed."""
        req = RouterRequest(query="b" * (MAX_QUERY_LENGTH - 1))
        assert len(req.query) == MAX_QUERY_LENGTH - 1


# ---------------------------------------------------------------------------
# map_validation_error_to_router_error — branch coverage
# ---------------------------------------------------------------------------

class TestValidationErrorMappingBranches:
    """Cover every branch in map_validation_error_to_router_error."""

    def test_whitespace_query_maps_to_query_empty(self):
        """Whitespace-only query should map to QUERY_EMPTY."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="   \n\t   ")
        
        code, msg = map_validation_error_to_router_error(exc_info.value)
        assert code == RouterErrorCode.QUERY_EMPTY

    def test_null_byte_query_maps_to_invalid_query(self):
        """Null-byte query should map to INVALID_QUERY."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="test\x00value")
        
        code, msg = map_validation_error_to_router_error(exc_info.value)
        assert code == RouterErrorCode.INVALID_QUERY
        assert "null" in msg.lower()

    def test_empty_errors_list_maps_to_invalid_request(self):
        """An empty errors list should fall back to INVALID_REQUEST."""

        class _FakeError:
            def errors(self):
                return []

        code, msg = map_validation_error_to_router_error(_FakeError())  # type: ignore[arg-type]
        assert code == RouterErrorCode.INVALID_REQUEST
        assert msg == "Request validation failed"

    def test_missing_query_field_maps_to_query_empty(self):
        """A missing 'query' field should map to QUERY_EMPTY."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest.model_validate({})
        
        code, msg = map_validation_error_to_router_error(exc_info.value)
        assert code == RouterErrorCode.QUERY_EMPTY

    def test_url_encoded_null_maps_to_invalid_query(self):
        """URL-encoded null byte (%00) should map to INVALID_QUERY."""
        with pytest.raises(ValidationError) as exc_info:
            RouterRequest(query="hello%00world")
        
        code, msg = map_validation_error_to_router_error(exc_info.value)
        assert code == RouterErrorCode.INVALID_QUERY


# ---------------------------------------------------------------------------
# Endpoint-level validation edge cases (async / integration)
# ---------------------------------------------------------------------------

class TestEndpointValidationEdgeCases:
    """Endpoint-level validation tests requiring the async client."""

    @pytest.mark.asyncio
    async def test_integer_query_in_json_rejected(self, client):
        """Sending an integer as 'query' should return 400 INVALID_QUERY."""
        response = await client.post(
            "/api/v1/query",
            json={"query": 12345},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] in [
            RouterErrorCode.INVALID_QUERY.value,
            RouterErrorCode.INVALID_REQUEST.value,
        ]

    @pytest.mark.asyncio
    async def test_extra_fields_in_body_accepted(self, client):
        """Extra unknown fields in the JSON body should be silently dropped."""
        response = await client.post(
            "/api/v1/query",
            json={
                "query": "valid query",
                "rogue_field": "should be ignored",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "valid query"
        assert "rogue_field" not in data

    @pytest.mark.asyncio
    async def test_empty_json_object_rejected(self, client):
        """An empty JSON object {} (missing required 'query') → 422."""
        response = await client.post(
            "/api/v1/query",
            json={},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_query_in_json_rejected(self, client):
        """Sending a list as 'query' should return 400."""
        response = await client.post(
            "/api/v1/query",
            json={"query": ["a", "b"]},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] in [
            RouterErrorCode.INVALID_QUERY.value,
            RouterErrorCode.INVALID_REQUEST.value,
        ]
