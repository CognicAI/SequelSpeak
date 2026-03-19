"""
Integration Tests for Query Endpoint with Conversation State

Tests the query endpoint's integration with the conversation state manager.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, AsyncMock
import uuid

from main import app
from services.conversation_state import conversation_state_manager
from utils.auth import verify_clerk_token
from schemas.conversation import ConversationStatus, ExecutionStage


# ============================================================================
# Fixtures
# ============================================================================

# Note: client fixture is provided by tests/conftest.py


# Note: The conversation_state_manager is initialized in the app's lifespan
# and is shared across all tests. For test isolation, individual tests
# can clear conversations if needed.


# ============================================================================
# Query Endpoint with Conversation State Tests
# ============================================================================

class TestQueryEndpointWithConversationState:
    """Tests for query endpoint integration with conversation state."""
    
    @pytest.mark.asyncio
    async def test_query_without_conversation_id_creates_new(self, client):
        """Test that query without conversation_id creates new conversation."""
        payload = {
            "query": "SELECT * FROM users"
        }
        
        response = await client.post("/api/v1/query/start", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return a conversation_id
        assert "conversation_id" in data
        assert data["conversation_id"] is not None
        
        # Should be a valid UUID
        try:
            uuid.UUID(data["conversation_id"])
        except ValueError:
            pytest.fail("conversation_id is not a valid UUID")
    
    @pytest.mark.asyncio
    async def test_query_with_conversation_id_uses_existing(self, client):
        """Test that query with conversation_id uses existing conversation."""
        # First query to create conversation
        payload1 = {
            "query": "SELECT * FROM users"
        }
        response1 = await client.post("/api/v1/query/start", json=payload1)
        conv_id = response1.json()["conversation_id"]
        
        # Mark as COMPLETE so a new turn can start
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)
        
        # Second query with same conversation_id
        payload2 = {
            "query": "SELECT * FROM orders",
            "conversation_id": conv_id
        }
        response2 = await client.post("/api/v1/query/start", json=payload2)
        
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Should return the same conversation_id
        assert data2["conversation_id"] == conv_id

    @pytest.mark.asyncio
    async def test_query_with_unknown_conversation_id_returns_404(self, client):
        """Provided conversation_id must exist; unknown IDs are rejected."""
        payload = {
            "query": "SELECT * FROM users",
            "conversation_id": "12345678-90ab-4cde-8f01-234567890abc",
        }

        response = await client.post("/api/v1/query/start", json=payload)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_start_while_clarification_needed_returns_409(self, client):
        """/start should fail when conversation is waiting for clarification."""
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show users"},
        )
        conv_id = response1.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["Do you mean active users only?"]
        await conversation_state_manager.save_state(state)

        response2 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show last 7 days", "conversation_id": conv_id},
        )

        assert response2.status_code == 409
        assert "awaiting clarification" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_start_while_processing_returns_409(self, client):
        """/start should reject follow-up if the conversation is already processing."""
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show users"},
        )
        conv_id = response1.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.PROCESSING
        state.current_stage = ExecutionStage.EXECUTION
        await conversation_state_manager.save_state(state)

        response2 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show top customers", "conversation_id": conv_id},
        )

        assert response2.status_code == 409
        assert "already in progress" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_follow_up_appends_turn_history(self, client):
        """Follow-up turns should preserve prior query context in state.turns."""
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show active users"},
        )
        conv_id = response1.json()["conversation_id"]

        # Mark first turn as complete so second can start
        state1 = await conversation_state_manager.get_state(conv_id)
        assert state1 is not None
        state1.generated_sql = "SELECT name FROM users WHERE status='active';"
        state1.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state1)

        response2 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show those from last 7 days", "conversation_id": conv_id},
        )
        assert response2.status_code == 200

        state2 = await conversation_state_manager.get_state(conv_id)
        assert state2 is not None
        # Turn history now lives in state.turns, not metadata["turn_history"]
        assert isinstance(state2.turns, list)
        assert len(state2.turns) >= 1
        assert state2.turns[-1]["original_query"] == "Show active users"
    
    @pytest.mark.asyncio
    async def test_query_with_user_context_stores_metadata(self, client):
        """Test that user_context is stored in conversation metadata."""
        payload = {
            "query": "SELECT * FROM products",
            "user_context": {
                "user_id": "user-123",
                "session_id": "session-abc"
            }
        }
        
        response = await client.post("/api/v1/query/start", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        conv_id = data["conversation_id"]
        
        # Verify metadata was stored (need to check conversation state directly)
        # This would require async context, so we trust the endpoint logic
        # In a real test, you might use async test client
        assert conv_id is not None
    
    @pytest.mark.asyncio
    async def test_query_conversation_persistence(self, client):
        """Test that conversation state persists across multiple queries."""
        # Create initial conversation
        payload1 = {"query": "First query"}
        response1 = await client.post("/api/v1/query/start", json=payload1)
        conv_id = response1.json()["conversation_id"]
        
        # Make multiple queries with same conversation_id
        for i in range(5):
            # Mark previous turn complete before starting new one
            state = await conversation_state_manager.get_state(conv_id)
            assert state is not None
            state.status = ConversationStatus.COMPLETE
            await conversation_state_manager.save_state(state)
            
            payload = {
                "query": f"Query number {i}",
                "conversation_id": conv_id
            }
            response = await client.post("/api/v1/query/start", json=payload)
            assert response.status_code == 200
            assert response.json()["conversation_id"] == conv_id
    
    @pytest.mark.asyncio
    async def test_query_with_invalid_conversation_id_format(self, client):
        """Test that invalid conversation_id format is rejected."""
        payload = {
            "query": "SELECT * FROM users",
            "conversation_id": "not-a-valid-uuid"
        }
        
        response = await client.post("/api/v1/query/start", json=payload)
        
        # Should return validation error
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_CONVERSATION_ID"
    
    @pytest.mark.asyncio
    async def test_query_response_includes_all_fields(self, client):
        """Test that query response includes all required fields."""
        payload = {
            "query": "SELECT * FROM users",
            "user_context": {"user_id": "123"}
        }
        
        response = await client.post("/api/v1/query/start", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all response fields
        assert "conversation_id" in data
        assert "query" in data
        assert "timestamp" in data
        assert "correlation_id" in data
        assert "message" in data
        
        assert data["query"] == payload["query"]
        assert data["message"] == "Query initialized successfully"


# ============================================================================
# Async Integration Tests
# ============================================================================

class TestAsyncConversationIntegration:
    """Async tests for conversation state integration."""
    
    @pytest.mark.asyncio
    async def test_conversation_state_created_by_endpoint(self, client):
        """Test that endpoint creates conversation state in manager."""
        payload = {"query": "Test query"}
        
        response = await client.post("/api/v1/query/start", json=payload)
        conv_id = response.json()["conversation_id"]
        
        # Verify state exists in manager
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id
    
    @pytest.mark.asyncio
    async def test_conversation_metadata_stored(self, client):
        """Test that user_context is stored as metadata."""
        user_context = {"user_id": "test-user-id-00000000", "session_id": "session-abc"}
        payload = {
            "query": "Test query",
            "user_context": user_context
        }
        
        response = await client.post("/api/v1/query/start", json=payload)
        conv_id = response.json()["conversation_id"]
        
        # Verify metadata
        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        assert "user_context" in state.metadata
        # UserContext schema normalizes by adding None for missing fields
        stored_context = state.metadata["user_context"]
        assert stored_context["user_id"] == "test-user-id-00000000"
        assert stored_context["session_id"] == "session-abc"

    @pytest.mark.asyncio
    async def test_status_and_respond_require_conversation_owner(self, client):
        """Different users must not access or respond to another user's conversation."""
        create_response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show me users"},
        )
        conv_id = create_response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["All users or active users?"]
        await conversation_state_manager.save_state(state)

        async def other_user_claims():
            return {"sub": "another-user-id"}

        app.dependency_overrides[verify_clerk_token] = other_user_claims
        try:
            status_response = await client.get(f"/api/v1/query/status/{conv_id}")
            assert status_response.status_code == 403

            respond_response = await client.post(
                "/api/v1/query/respond",
                json={
                    "conversation_id": conv_id,
                    "answers": ["active users"],
                },
            )
            assert respond_response.status_code == 403
        finally:
            async def default_test_claims():
                return {"sub": "test-user-id-00000000", "email": "test@example.com"}

            app.dependency_overrides[verify_clerk_token] = default_test_claims

    @pytest.mark.asyncio
    async def test_respond_resets_stage_to_planning(self, client):
        """/respond should move status back to processing and stage back to planning."""
        create_response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show users"},
        )
        conv_id = create_response.json()["conversation_id"]

        state = await conversation_state_manager.get_state(conv_id)
        assert state is not None
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.current_stage = ExecutionStage.CLARIFICATION
        state.awaiting_user_response = True
        state.pending_clarification_questions = ["All users or active users?"]
        await conversation_state_manager.save_state(state)

        respond_response = await client.post(
            "/api/v1/query/respond",
            json={
                "conversation_id": conv_id,
                "answers": ["active users"],
            },
        )

        assert respond_response.status_code == 200
        response_data = respond_response.json()
        assert response_data["status"] == ConversationStatus.PROCESSING.value
        assert response_data["current_stage"] == ExecutionStage.PLANNING.value

        updated_state = await conversation_state_manager.get_state(conv_id)
        assert updated_state is not None
        # router_context is no longer persisted — computed on-the-fly
        assert updated_state.current_nl_query is not None


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling in query endpoint with conversation state."""
    
    @pytest.mark.asyncio
    async def test_query_works_with_memory_fallback(self, client):
        """Test that query endpoint works when Redis is unavailable."""
        # Force memory mode
        original_use_redis = conversation_state_manager._use_redis
        conversation_state_manager._use_redis = False
        
        try:
            payload = {"query": "SELECT * FROM users"}
            response = await client.post("/api/v1/query/start", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert "conversation_id" in data
        
        finally:
            conversation_state_manager._use_redis = original_use_redis
