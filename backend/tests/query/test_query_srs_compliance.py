"""
Tests for SRS v2.1 compliance gaps in the query endpoint.

Covers:
  - FR-83: Cancel endpoint
  - FR-82: Clarification timeout
  - FR-87: Clarification round limit
  - FR-78: Resume from paused_at_stage
  - Answer validation edge case
  - Retry endpoint
  - Database ID single save (race condition fix)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any, cast
from httpx import AsyncClient, Response

from services.conversation_state import conversation_state_manager
from schemas.conversation import ConversationStatus, ExecutionStage


# Note: client fixture is provided by tests/conftest.py


def _response_json(response: Response) -> dict[str, Any]:
    """Return typed JSON object for HTTP responses in tests."""
    return cast(dict[str, Any], response.json())


def _conversation_id(response: Response) -> str:
    """Extract conversation_id as str from a /start response."""
    return str(_response_json(response)["conversation_id"])


# ============================================================================
# FR-83: Cancel Endpoint Tests
# ============================================================================

class TestCancelEndpoint:
    """Tests for POST /api/v1/query/cancel/{conversation_id} (FR-83)."""

    @pytest.mark.asyncio
    async def test_cancel_active_conversation(self, client: AsyncClient):
        """Cancel a conversation that is currently processing."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        assert response.status_code == 200
        conv_id = _conversation_id(response)

        # Ensure state is PROCESSING
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.PROCESSING
        state.current_stage = ExecutionStage.EXECUTION
        await conversation_state_manager.save_state(state)

        # Cancel it
        cancel_response = await client.post(f"/api/v1/query/cancel/{conv_id}")
        assert cancel_response.status_code == 200
        data = _response_json(cancel_response)
        assert data["status"] == "cancelled"
        assert data["conversation_id"] == conv_id

        # Verify state updated
        updated = await conversation_state_manager.get_state(conv_id)
        assert updated is not None
        assert updated.status == ConversationStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_clarification_conversation(self, client: AsyncClient):
        """Cancel a conversation that is waiting for clarification."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        await conversation_state_manager.save_state(state)

        cancel_response = await client.post(f"/api/v1/query/cancel/{conv_id}")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_idempotent_on_already_cancelled(self, client: AsyncClient):
        """Cancelling an already-cancelled conversation should succeed (idempotent)."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CANCELLED
        state.current_stage = ExecutionStage.CANCELLED
        await conversation_state_manager.save_state(state)

        cancel_response = await client.post(f"/api/v1/query/cancel/{conv_id}")
        assert cancel_response.status_code == 200
        data = _response_json(cancel_response)
        assert data["status"] == "cancelled"
        assert data["message"] == "Conversation was already cancelled"

    @pytest.mark.asyncio
    async def test_cancel_terminal_state_rejected(self, client: AsyncClient):
        """Cannot cancel a completed conversation."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)

        cancel_response = await client.post(f"/api/v1/query/cancel/{conv_id}")
        assert cancel_response.status_code == 409
        assert "terminal state" in str(_response_json(cancel_response)["detail"]).lower()

    @pytest.mark.asyncio
    async def test_cancel_not_found_returns_404(self, client: AsyncClient):
        """Cancelling a non-existent conversation returns 404."""
        cancel_response = await client.post(
            "/api/v1/query/cancel/00000000-0000-4000-a000-000000000000"
        )
        assert cancel_response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_requires_owner(self, client: AsyncClient):
        """Cancel should reject non-owner requests."""
        from main import app
        from utils.auth import verify_clerk_token

        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.PROCESSING
        await conversation_state_manager.save_state(state)

        # Switch to different user
        async def other_user_claims():
            return {"sub": "another-user-id"}

        app.dependency_overrides[verify_clerk_token] = other_user_claims
        try:
            cancel_response = await client.post(f"/api/v1/query/cancel/{conv_id}")
            assert cancel_response.status_code == 403
        finally:
            async def default_test_claims():
                return {"sub": "test-user-id-00000000", "email": "test@example.com"}
            app.dependency_overrides[verify_clerk_token] = default_test_claims


# ============================================================================
# FR-82: Clarification Timeout Tests
# ============================================================================

class TestClarificationTimeout:
    """Tests for FR-82: 30-minute timeout on paused conversations."""

    @pytest.mark.asyncio
    async def test_timeout_on_respond(self, client: AsyncClient):
        """Responding to a timed-out clarification should return 410 Gone."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        # Set updated_at to 31 minutes ago to trigger timeout
        expired = (datetime.now(timezone.utc) - timedelta(minutes=31))
        state.updated_at = expired.isoformat().replace('+00:00', 'Z')
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 410
        assert "timed out" in str(_response_json(respond_response)["detail"]).lower()

        # Verify state transitioned to TIMEOUT
        updated = await conversation_state_manager.get_state(conv_id)
        assert updated is not None
        assert updated.status == ConversationStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_no_timeout_within_window(self, client: AsyncClient):
        """Responding within the timeout window should succeed."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        # Set updated_at to 5 minutes ago (well within window)
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5))
        state.updated_at = recent.isoformat().replace('+00:00', 'Z')
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 200

    @pytest.mark.asyncio
    async def test_timeout_on_start_existing_conv(self, client: AsyncClient):
        """Starting a query on a timed-out conversation should return 410 Gone."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        expired = (datetime.now(timezone.utc) - timedelta(minutes=31))
        state.updated_at = expired.isoformat().replace('+00:00', 'Z')
        await conversation_state_manager.save_state(state)

        start_response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me active users", "conversation_id": conv_id},
        )
        assert start_response.status_code == 410
        assert "timed out" in str(_response_json(start_response)["detail"]).lower()


# ============================================================================
# FR-87: Clarification Round Limit Tests
# ============================================================================

class TestClarificationRoundLimit:
    """Tests for FR-87: 3-round clarification limit."""

    @pytest.mark.asyncio
    async def test_exceed_max_rounds_rejected(self, client: AsyncClient):
        """Exceeding 3 clarification rounds should be rejected."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        state.clarification_rounds = 3  # Already at max
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 422
        detail = str(_response_json(respond_response)["detail"]).lower()
        assert "maximum" in detail or "exceeded" in detail

    @pytest.mark.asyncio
    async def test_within_rounds_accepted(self, client: AsyncClient):
        """Rounds within the limit should be accepted."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        state.clarification_rounds = 1  # Still has room
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 200


# ============================================================================
# FR-78: Resume from paused_at_stage Tests
# ============================================================================

class TestResumeFromPausedStage:
    """Tests for FR-78/FR-86: Resume from paused_at_stage."""

    @pytest.mark.asyncio
    async def test_respond_resumes_from_paused_stage(self, client: AsyncClient):
        """/respond should use _paused_at_stage from metadata if available."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.current_stage = ExecutionStage.CLARIFICATION
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        # Simulate orchestrator setting the paused stage
        state.metadata['_paused_at_stage'] = ExecutionStage.SCHEMA_RETRIEVAL.value
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 200
        data = _response_json(respond_response)
        assert data["current_stage"] == ExecutionStage.SCHEMA_RETRIEVAL.value

    @pytest.mark.asyncio
    async def test_respond_defaults_to_planning_without_paused_stage(self, client: AsyncClient):
        """/respond falls back to PLANNING when _paused_at_stage is absent."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.current_stage = ExecutionStage.CLARIFICATION
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        # No _paused_at_stage set
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )
        assert respond_response.status_code == 200
        data = _response_json(respond_response)
        assert data["current_stage"] == ExecutionStage.PLANNING.value


# ============================================================================
# Answer Validation Edge Case Tests
# ============================================================================

class TestAnswerValidation:
    """Tests for answer validation edge cases."""

    @pytest.mark.asyncio
    async def test_respond_rejects_empty_answers_and_no_message(self, client: AsyncClient):
        """Both empty answers and missing message should be rejected."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": [],
            },
        )
        assert respond_response.status_code == 422
        assert "must provide" in str(_response_json(respond_response)["detail"]).lower()

    @pytest.mark.asyncio
    async def test_respond_accepts_message_fallback(self, client: AsyncClient):
        """Message-only (no answers) should be accepted as fallback."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Which users?"]
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": [],
                "message": "I want active users from last month",
            },
        )
        assert respond_response.status_code == 200


# ============================================================================
# Retry Endpoint Tests
# ============================================================================

class TestRetryEndpoint:
    """Tests for POST /api/v1/query/retry/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_retry_error_conversation(self, client: AsyncClient):
        """Retry should work for conversations in error state."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.ERROR
        state.errors = [{"message": "LLM API timeout"}]
        await conversation_state_manager.save_state(state)

        retry_response = await client.post(f"/api/v1/query/retry/{conv_id}")
        assert retry_response.status_code == 200
        data = _response_json(retry_response)
        assert data["status"] == ConversationStatus.PROCESSING.value
        assert data["current_stage"] == ExecutionStage.PLANNING.value

        # Verify errors cleared
        updated = await conversation_state_manager.get_state(conv_id)
        assert updated is not None
        assert updated.errors == []

    @pytest.mark.asyncio
    async def test_retry_non_error_rejected(self, client: AsyncClient):
        """Retry should be rejected for non-error conversations."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.PROCESSING
        await conversation_state_manager.save_state(state)

        retry_response = await client.post(f"/api/v1/query/retry/{conv_id}")
        assert retry_response.status_code == 409
        assert "error" in str(_response_json(retry_response)["detail"]).lower()

    @pytest.mark.asyncio
    async def test_retry_not_found_returns_404(self, client: AsyncClient):
        """Retrying a non-existent conversation returns 404."""
        retry_response = await client.post(
            "/api/v1/query/retry/00000000-0000-4000-a000-000000000000"
        )
        assert retry_response.status_code == 404


# ============================================================================
# Database ID Race Condition Test
# ============================================================================

class TestDatabaseIdSingleSave:
    """Test that database_id is set before the first save (no extra roundtrip)."""

    @pytest.mark.asyncio
    async def test_database_id_stored_on_new_conversation(self, client: AsyncClient):
        """database_id should be in metadata after initial save."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show me users",
                "database_id": "db-test-123",
            },
        )
        assert response.status_code == 200
        conv_id = _conversation_id(response)

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert state.metadata.get("database_id") == "db-test-123"

    @pytest.mark.asyncio
    async def test_database_id_stored_on_existing_conversation(self, client: AsyncClient):
        """database_id should be updated on existing conversation follow-up."""
        # Create conversation
        r1 = await client.post("/api/v1/query/start", json={"query": "Initial"})
        conv_id = _conversation_id(r1)

        # Mark complete so follow-up works
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)

        # Follow-up with database_id
        r2 = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Follow up",
                "conversation_id": conv_id,
                "database_id": "db-new-456",
            },
        )
        assert r2.status_code == 200

        updated = await conversation_state_manager.get_state(conv_id)
        assert updated is not None
        assert updated.metadata.get("database_id") == "db-new-456"
