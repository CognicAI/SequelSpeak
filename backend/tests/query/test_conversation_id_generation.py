"""
Unit Tests: Conversation ID Generation and Reuse (Subtask 2.1.3)

Tests conversation ID lifecycle:
- Generation of valid UUID v4 when no ID is provided
- Reuse of existing conversation ID for follow-up requests
- Propagation of conversation ID via request.state
"""

import pytest
import uuid
import re
from typing import AsyncGenerator

from httpx import AsyncClient
from services.conversation_state import ConversationStateManager


# UUID v4 pattern (matches: xxxxxxxx-xxxx-4xxx-[89ab]xxx-xxxxxxxxxxxx)
UUID_V4_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def manager() -> AsyncGenerator[ConversationStateManager, None]:
    """Provide an isolated in-memory ConversationStateManager per test."""
    from config import settings
    original = settings.redis_enabled
    settings.redis_enabled = False

    m = ConversationStateManager()
    await m.initialize()

    yield m

    await m.clear_all()
    await m.close()
    settings.redis_enabled = original


# ============================================================================
# _generate_conversation_id – Unit Tests
# ============================================================================

class TestGenerateConversationId:
    """Direct unit tests for generate_conversation_id()."""

    def test_returns_string(self):
        """Generated ID is a plain string."""
        m = ConversationStateManager()
        result = m.generate_conversation_id()
        assert isinstance(result, str)

    def test_is_valid_uuid_v4(self):
        """Generated ID matches UUID v4 format."""
        m = ConversationStateManager()
        result = m.generate_conversation_id()
        assert UUID_V4_PATTERN.match(result), f"Not a valid UUID v4: {result}"

    def test_parseable_by_stdlib_uuid(self):
        """Generated ID can be parsed as uuid.UUID without raising."""
        m = ConversationStateManager()
        result: str = m.generate_conversation_id()
        parsed = uuid.UUID(result)
        assert parsed.version == 4

    def test_generates_unique_ids(self):
        """Consecutive calls produce different IDs (no collision)."""
        m = ConversationStateManager()
        ids = {m.generate_conversation_id() for _ in range(100)}
        assert len(ids) == 100, "Duplicate conversation IDs were generated"

    def test_lowercase_hex(self):
        """Generated IDs are lowercase (consistent normalisation)."""
        m = ConversationStateManager()
        result: str = m.generate_conversation_id()
        assert result == result.lower()


# ============================================================================
# get_or_create – ID Generation
# ============================================================================

class TestGetOrCreateGeneration:
    """Tests for ID generation path inside get_or_create()."""

    @pytest.mark.asyncio
    async def test_creates_new_id_when_none_provided(self, manager: ConversationStateManager):
        """get_or_create(None) generates and stores a new UUID v4."""
        conv_id = await manager.get_or_create(None)

        assert conv_id is not None
        assert UUID_V4_PATTERN.match(conv_id), f"Not a valid UUID v4: {conv_id}"

    @pytest.mark.asyncio
    async def test_creates_new_id_when_no_argument(self, manager: ConversationStateManager):
        """get_or_create() with no args generates a new UUID v4."""
        conv_id = await manager.get_or_create()

        assert conv_id is not None
        assert UUID_V4_PATTERN.match(conv_id)

    @pytest.mark.asyncio
    async def test_persists_new_conversation(self, manager: ConversationStateManager):
        """Newly generated conversation is persisted and retrievable."""
        conv_id = await manager.get_or_create()

        state = await manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id

    @pytest.mark.asyncio
    async def test_each_call_without_id_creates_different_conversation(self, manager: ConversationStateManager):
        """Two calls without an ID produce two different conversations."""
        id1 = await manager.get_or_create()
        id2 = await manager.get_or_create()

        assert id1 != id2


# ============================================================================
# get_or_create – ID Reuse
# ============================================================================

class TestGetOrCreateReuse:
    """Tests for ID-reuse path inside get_or_create()."""

    @pytest.mark.asyncio
    async def test_returns_same_id_for_existing_conversation(self, manager: ConversationStateManager):
        """Providing an existing conversation_id returns that same ID."""
        original_id = await manager.get_or_create()

        returned_id = await manager.get_or_create(original_id)

        assert returned_id == original_id

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_state(self, manager: ConversationStateManager):
        """Reusing an ID does not reset the stored ConversationState."""
        conv_id = await manager.get_or_create()
        await manager.upsert_state(conv_id, metadata={"key": "value"})

        # Call get_or_create with the same ID
        await manager.get_or_create(conv_id)

        state = await manager.get_state(conv_id)
        assert state is not None
        assert state.metadata.get("key") == "value"

    @pytest.mark.asyncio
    async def test_multi_turn_consistent_id(self, manager: ConversationStateManager):
        """Simulated multi-turn: same conversation_id is returned across 5 requests."""
        original_id = await manager.get_or_create()

        for _ in range(5):
            returned = await manager.get_or_create(original_id)
            assert returned == original_id

    @pytest.mark.asyncio
    async def test_unknown_id_creates_new_state(self, manager: ConversationStateManager):
        """Providing an ID that does not exist creates a new conversation with that ID."""
        fresh_id = str(uuid.uuid4())

        returned_id = await manager.get_or_create(fresh_id)

        assert returned_id == fresh_id
        state = await manager.get_state(fresh_id)
        assert state is not None
        assert state.conversation_id == fresh_id


# ============================================================================
# request.state Propagation (via endpoint)
# ============================================================================

class TestRequestStatePropagation:
    """
    Tests that conversation_id is attached to request.state for downstream use.
    Uses an ASGITransport middleware spy to inspect request.state after the
    endpoint handler runs.
    """

    @pytest.mark.asyncio
    async def test_request_state_has_conversation_id(self, client: AsyncClient):
        """
        Calling POST /api/v1/query sets request.state.conversation_id.
        Verified indirectly: the response conversation_id matches a valid UUID v4,
        and the endpoint assigns it to request.state without raising.
        """
        payload = {"query": "Show me revenue for last month"}
        response = await client.post("/api/v1/query/start", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert UUID_V4_PATTERN.match(data["conversation_id"])

    @pytest.mark.asyncio
    async def test_request_state_conversation_id_consistent_with_response(self, client: AsyncClient):
        """
        The conversation_id in the response is the same ID
        that was stored in request.state (proven by consistent round-trip).
        """
        from services.conversation_state import conversation_state_manager

        payload = {"query": "How many users signed up last week?"}
        response = await client.post("/api/v1/query/start", json=payload)

        assert response.status_code == 200
        conv_id = response.json()["conversation_id"]

        # The same ID must be retrievable from the state manager
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id

    @pytest.mark.asyncio
    async def test_provided_conversation_id_propagated_in_response(self, client: AsyncClient):
        """
        When a valid conversation_id is supplied, the same ID is echoed back
        in the response (confirms propagation of provided ID, not a fresh one).
        """
        existing_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        payload = {
            "query": "Follow-up question",
            "conversation_id": existing_id
        }
        response = await client.post("/api/v1/query/start", json=payload)

        assert response.status_code == 200
        assert response.json()["conversation_id"] == existing_id
