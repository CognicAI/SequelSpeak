"""
Unit and Integration Tests: User/Session Metadata Attachment (Subtask 2.1.x)

Covers:
- sanitize_user_context_for_log() excludes sensitive fields
- UserContext.safe_dict() excludes sensitive fields
- ip_address auto-enrichment from request.client.host
- Full metadata (including ip_address) persisted to ConversationState
- request.state.user_context set for downstream persona access
- ip_address never appears in structured log output
"""

import logging
import pytest
from typing import Any

from httpx import AsyncClient

from schemas.router import UserContext
from utils.security import sanitize_user_context_for_log, SENSITIVE_USER_CONTEXT_FIELDS
from services.conversation_state import conversation_state_manager


# ============================================================================
# Unit Tests: sanitize_user_context_for_log()
# ============================================================================

class TestSanitizeUserContextForLog:
    """Tests for utils.security.sanitize_user_context_for_log()."""

    def test_removes_ip_address(self) -> None:
        """ip_address must be stripped from the returned dict."""
        raw = {"user_id": "u1", "session_id": "s1", "ip_address": "192.168.1.1"}
        result = sanitize_user_context_for_log(raw)
        assert "ip_address" not in result

    def test_retains_non_sensitive_fields(self) -> None:
        """user_id and session_id must be present after sanitization."""
        raw = {"user_id": "u1", "session_id": "s1", "ip_address": "10.0.0.1"}
        result = sanitize_user_context_for_log(raw)
        assert result["user_id"] == "u1"
        assert result["session_id"] == "s1"

    def test_safe_on_dict_without_sensitive_fields(self) -> None:
        """No error when sensitive fields are already absent."""
        raw = {"user_id": "u2"}
        result = sanitize_user_context_for_log(raw)
        assert result == {"user_id": "u2"}

    def test_safe_on_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        assert sanitize_user_context_for_log({}) == {}

    def test_does_not_mutate_original(self) -> None:
        """Original dict is not modified."""
        raw = {"user_id": "u3", "ip_address": "1.2.3.4"}
        sanitize_user_context_for_log(raw)
        assert "ip_address" in raw

    def test_sensitive_fields_constant_contains_ip_address(self) -> None:
        """SENSITIVE_USER_CONTEXT_FIELDS must include ip_address."""
        assert "ip_address" in SENSITIVE_USER_CONTEXT_FIELDS


# ============================================================================
# Unit Tests: UserContext.safe_dict()
# ============================================================================

class TestUserContextSafeDict:
    """Tests for schemas.router.UserContext.safe_dict()."""

    def test_excludes_ip_address(self) -> None:
        """safe_dict() must not include ip_address."""
        ctx = UserContext(user_id="u1", session_id="s1", ip_address="10.0.0.1")
        result = ctx.safe_dict()
        assert "ip_address" not in result

    def test_includes_user_id(self) -> None:
        """safe_dict() includes user_id."""
        ctx = UserContext(user_id="u-abc", session_id=None, ip_address="10.0.0.1")
        assert ctx.safe_dict()["user_id"] == "u-abc"

    def test_includes_session_id(self) -> None:
        """safe_dict() includes session_id."""
        ctx = UserContext(user_id=None, session_id="sess-xyz", ip_address="10.0.0.1")
        assert ctx.safe_dict()["session_id"] == "sess-xyz"

    def test_model_dump_includes_ip(self) -> None:
        """model_dump() (used for persistence) DOES include ip_address."""
        ctx = UserContext(user_id=None, session_id=None, ip_address="1.2.3.4")
        assert ctx.model_dump()["ip_address"] == "1.2.3.4"

    def test_safe_dict_without_ip_set(self) -> None:
        """safe_dict() works when ip_address is None."""
        ctx = UserContext(user_id="u1", session_id=None, ip_address=None)
        result = ctx.safe_dict()
        assert "ip_address" not in result


# ============================================================================
# Integration Tests: Endpoint metadata attachment behavior
# ============================================================================

class TestMetadataAttachmentEndpoint:
    """
    Integration tests for POST /api/v1/query metadata lifecycle.

    Verifies that:
    - ip_address is auto-enriched from the request.client when not supplied
    - Full metadata (incl. ip_address) is persisted to ConversationState
    - Safe metadata (no ip_address) is used in log output
    """

    @pytest.mark.asyncio
    async def test_full_metadata_stored_in_conversation_state(self, client: AsyncClient) -> None:
        """Full user_context including ip_address is persisted to ConversationState."""
        payload: dict[str, Any] = {
            "query": "Show total sales",
            "user_context": {
                "user_id": "test-user-id-00000000",
                "session_id": "sess-store-test",
                "ip_address": "203.0.113.1"
            }
        }

        response = await client.post("/api/v1/query/start", json=payload)
        assert response.status_code == 200
        conv_id: str = response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        stored_ctx = state.metadata["user_context"]

        assert stored_ctx["user_id"] == "test-user-id-00000000"
        assert stored_ctx["session_id"] == "sess-store-test"
        assert stored_ctx["ip_address"] == "203.0.113.1"

    @pytest.mark.asyncio
    async def test_ip_address_auto_populated_from_request_client(self, client: AsyncClient) -> None:
        """When ip_address is absent from payload, it is populated from request.client.host."""
        payload: dict[str, Any] = {
            "query": "Count active users",
            "user_context": {
                "user_id": "user-ip-test",
                "session_id": None
                # ip_address intentionally omitted
            }
        }

        response = await client.post("/api/v1/query/start", json=payload)
        assert response.status_code == 200
        conv_id: str = response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        stored_ctx = state.metadata["user_context"]

        # ip_address must have been filled in (testclient uses "testclient" host)
        assert stored_ctx.get("ip_address") is not None

    @pytest.mark.asyncio
    async def test_explicit_ip_not_overwritten(self, client: AsyncClient) -> None:
        """An explicitly supplied ip_address is preserved, not replaced by request.client.host."""
        explicit_ip = "192.0.2.55"
        payload: dict[str, Any] = {
            "query": "Fetch recent orders",
            "user_context": {
                "user_id": "user-explicit-ip",
                "ip_address": explicit_ip
            }
        }

        response = await client.post("/api/v1/query/start", json=payload)
        assert response.status_code == 200
        conv_id: str = response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert state.metadata["user_context"]["ip_address"] == explicit_ip

    @pytest.mark.asyncio
    async def test_metadata_available_without_explicit_user_context(self, client: AsyncClient) -> None:
        """Endpoint persists metadata even when user_context is omitted from request."""
        payload = {"query": "What is the average order value?"}

        response = await client.post("/api/v1/query/start", json=payload)
        assert response.status_code == 200
        conv_id: str = response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert "user_context" in state.metadata

    @pytest.mark.asyncio
    async def test_explicit_null_user_context_does_not_crash(self, client: AsyncClient) -> None:
        """Sending user_context: null explicitly must not raise AttributeError."""
        payload: dict[str, Any] = {
            "query": "How many orders were placed today?",
            "user_context": None,
        }

        response = await client.post("/api/v1/query/start", json=payload)
        # null is treated the same as omitting user_context — should succeed
        assert response.status_code == 200

        conv_id: str = response.json()["conversation_id"]
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        # A default UserContext() should have been created and persisted
        assert "user_context" in state.metadata

    @pytest.mark.asyncio
    async def test_ip_address_not_in_log_output(self, client: AsyncClient) -> None:
        """ip_address must never appear in any logger.info call during the request."""
        ip_to_guard = "10.20.30.40"
        payload: dict[str, Any] = {
            "query": "Revenue breakdown by region",
            "user_context": {
                "user_id": "user-log-guard",
                "ip_address": ip_to_guard
            }
        }

        log_messages: list[str] = []

        class CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_messages.append(self.format(record))

        handler = CapturingHandler()
        logging.getLogger("api.v1.query").addHandler(handler)
        try:
            response = await client.post("/api/v1/query/start", json=payload)
            assert response.status_code == 200
        finally:
            logging.getLogger("api.v1.query").removeHandler(handler)

        for msg in log_messages:
            assert ip_to_guard not in msg, (
                f"ip_address '{ip_to_guard}' leaked into log message: {msg}"
            )


# ============================================================================
# Downstream Availability: request.state.user_context
# ============================================================================

class TestRequestStateUserContext:
    """
    Verify that user_context is attached to request.state.

    Tested indirectly: the endpoint sets request.state.user_context and the
    value is verifiable via ConversationState round-trip (same data source).
    """

    @pytest.mark.asyncio
    async def test_user_context_persisted_matches_request_payload(self, client: AsyncClient) -> None:
        """The persisted user_context equals the data set on request.state."""
        payload: dict[str, Any] = {
            "query": "Top 10 customers by revenue",
            "user_context": {
                "user_id": "test-user-id-00000000",
                "session_id": "sess-state-check",
                "ip_address": "172.16.0.1"
            }
        }

        response = await client.post("/api/v1/query/start", json=payload)
        assert response.status_code == 200
        conv_id: str = response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        ctx = state.metadata["user_context"]

        assert ctx["user_id"] == "test-user-id-00000000"
        assert ctx["session_id"] == "sess-state-check"
        assert ctx["ip_address"] == "172.16.0.1"

    @pytest.mark.asyncio
    async def test_metadata_stable_across_multi_turn(self, client: AsyncClient) -> None:
        """Metadata persisted in first turn is retrievable in subsequent turns."""
        payload_turn1: dict[str, Any] = {
            "query": "First turn query",
            "user_context": {"user_id": "test-user-id-00000000", "session_id": "mt-sess"}
        }
        r1 = await client.post("/api/v1/query/start", json=payload_turn1)
        assert r1.status_code == 200
        conv_id: str = r1.json()["conversation_id"]

        # Second turn — same conversation, different query, no user_context re-sent
        payload_turn2: dict[str, Any] = {
            "query": "Follow-up query",
            "conversation_id": conv_id
        }
        r2 = await client.post("/api/v1/query/start", json=payload_turn2)
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == conv_id

        # State from first turn should still be intact
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert state.metadata["user_context"]["user_id"] == "test-user-id-00000000"
