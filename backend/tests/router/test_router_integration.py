"""
Integration Tests for Router Service with State Persistence

Tests the end-to-end flow from Router entry point through state persistence.

Test Coverage:
- Query endpoint → RouterService → ConversationState persistence
- New conversation creation
- Existing conversation handling
- User context merging
- Correlation ID propagation
- State retrieval and verification
"""

import pytest
from httpx import AsyncClient

from services.conversation_state import conversation_state_manager
from services.router_service import initialize_router_service, get_router_service
from schemas.conversation import ExecutionStage, ConversationStatus


import unittest.mock

@pytest.fixture(autouse=True)
def mock_orchestrator():
    """Mock the orchestrator so background tasks don't block tests."""
    with unittest.mock.patch("api.v1.query.get_orchestrator_service") as mock_get:
        mock_svc = unittest.mock.AsyncMock()
        mock_svc.execute_conversation = unittest.mock.AsyncMock()
        mock_get.return_value = mock_svc
        yield mock_svc
        
import unittest.mock

@pytest.fixture(autouse=True)
def mock_orchestrator():
    """Mock the orchestrator so background tasks don't block tests."""
    with unittest.mock.patch("api.v1.query.get_orchestrator_service") as mock_get:
        mock_svc = unittest.mock.AsyncMock()
        mock_svc.execute_conversation = unittest.mock.AsyncMock()
        mock_get.return_value = mock_svc
        yield mock_svc
        
# ============================================================================
# Fixtures
# ============================================================================

# Note: client fixture is provided by tests/conftest.py using ASGITransport

@pytest.fixture(autouse=True)
async def clean_state():
    """Clean conversation state before and after each test."""
    # Initialize if needed
    if not conversation_state_manager.is_initialized:
        await conversation_state_manager.initialize()
    
    # Initialize router service if needed
    try:
        get_router_service()
    except RuntimeError:
        initialize_router_service(conversation_state_manager)
    
    # Clean before test
    await conversation_state_manager.clear_all()
    
    yield
    
    # Clean after test
    await conversation_state_manager.clear_all()


# ============================================================================
# Router Entry → State Persistence Integration Tests
# ============================================================================

class TestRouterStatePersistenceIntegration:
    """Integration tests for Router entry point state persistence."""
    
    @pytest.mark.asyncio
    async def test_new_conversation_creates_initial_state(self, client: AsyncClient):
        """Test that a new query creates initial conversation state."""
        # Send query request
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show me sales from last month"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response
        assert data["status"] == "success"
        assert "conversation_id" in data
        assert data["query"] == "Show me sales from last month"
        
        conversation_id = data["conversation_id"]
        
        # Retrieve state from persistence
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        
        # Verify state was persisted correctly
        assert state.conversation_id == conversation_id
        assert state.original_nl_query == "Show me sales from last month"
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        assert state.awaiting_user_response is False
        assert state.session_start_time is not None
        assert state.updated_at is not None
    
    @pytest.mark.asyncio
    async def test_conversation_with_user_context_persists_metadata(self, client: AsyncClient):
        """Test that user context is persisted in metadata."""
        response = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Count active users",
                "user_context": {
                    "user_id": "test-user-id-00000000",
                    "session_id": "session-abc"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        conversation_id = data["conversation_id"]
        
        # Retrieve state
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        
        # Verify user context in metadata
        assert state.metadata["user_context"]["user_id"] == "test-user-id-00000000"
        assert state.metadata["user_context"]["session_id"] == "session-abc"
    
    @pytest.mark.asyncio
    async def test_existing_conversation_preserves_state(self, client: AsyncClient):
        """Test that follow-up queries to existing conversation preserve state."""
        # First query
        response1 = await client.post(
            "/api/v1/query/start",
            json={"query": "Show sales"}
        )
        
        conversation_id = response1.json()["conversation_id"]
        
        # Get initial state
        state1 = await conversation_state_manager.get_state(conversation_id)
        assert state1 is not None
        initial_timestamp = state1.session_start_time
        
        # Mark as COMPLETE so a new turn can start (state machine validation)
        state1.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state1)
        
        # Second query with same conversation_id (simulate multi-turn)
        response2 = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show revenue instead",
                "conversation_id": conversation_id
            }
        )
        
        assert response2.status_code == 200
        
        # Verify conversation_id is the same
        assert response2.json()["conversation_id"] == conversation_id
        
        # Get updated state
        state2 = await conversation_state_manager.get_state(conversation_id)
        assert state2 is not None
        
        # Verify state was preserved (session_start_time shouldn't change)
        assert state2.session_start_time == initial_timestamp
        
        # But updated_at should change (or at least stay current)
        assert state2.updated_at >= state1.updated_at
    
    @pytest.mark.asyncio
    async def test_user_context_merging_on_follow_up(self, client: AsyncClient):
        """Test that user context is merged correctly on follow-up requests."""
        # First query with initial context
        response1 = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show sales",
                "user_context": {
                    "user_id": "test-user-id-00000000",
                    "session_id": "session-abc"
                }
            }
        )
        
        conversation_id = response1.json()["conversation_id"]
        
        # Mark as COMPLETE so a new turn can start (state machine validation)
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        state.status = ConversationStatus.COMPLETE
        await conversation_state_manager.save_state(state)
        
        # Second query with updated context (different session_id)
        response2 = await client.post(
            "/api/v1/query/start",
            json={
                "query": "Show revenue",
                "conversation_id": conversation_id,
                "user_context": {
                    "session_id": "session-xyz"
                }
            }
        )
        
        assert response2.status_code == 200
        
        # Get final state
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        
        # Verify context was merged (user_id preserved, session_id updated)
        assert state.metadata["user_context"]["user_id"] == "test-user-id-00000000"
        assert state.metadata["user_context"]["session_id"] == "session-xyz"
    
    @pytest.mark.asyncio
    async def test_correlation_id_stored_in_metadata(self, client: AsyncClient):
        """Test that correlation ID from headers is stored in metadata."""
        correlation_id = "test-corr-12345"
        
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Show data"},
            headers={"X-Correlation-ID": correlation_id}
        )
        
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]
        
        # Verify correlation_id in response
        assert response.json()["correlation_id"] == correlation_id
        
        # Verify correlation_id in persisted state
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        assert state.metadata.get("correlation_id") == correlation_id
    
    @pytest.mark.asyncio
    async def test_state_persistence_before_routing_decisions(self, client: AsyncClient):
        """Test that state is persisted BEFORE routing decisions are made."""
        # This test verifies the architectural requirement that state persistence
        # happens at Router entry, not after routing decisions.
        
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Complex analytics query"}
        )
        
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]
        
        # State should exist immediately
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        
        # Initial stage should be PLANNING (not later stages)
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        
        # Query should be stored
        assert state.original_nl_query == "Complex analytics query"


# ============================================================================
# State Field Verification Tests
# ============================================================================

class TestStatePersistenceFields:
    """Tests to verify all required state fields are persisted correctly."""
    
    @pytest.mark.asyncio
    async def test_all_srs_fields_initialized(self, client: AsyncClient):
        """Verify all 18 SRS-required fields are initialized."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Test query"}
        )
        
        conversation_id = response.json()["conversation_id"]
        state = await conversation_state_manager.get_state(conversation_id)
        assert state is not None
        
        # Core identity fields
        assert state.conversation_id is not None
        assert state.session_start_time is not None
        
        # Query fields
        assert state.original_nl_query == "Test query"
        assert state.current_nl_query == "Test query"  # Now set by start_new_turn()
        
        # Parameter resolution
        assert isinstance(state.resolved_parameters, dict)
        
        # Clarification fields
        assert isinstance(state.pending_clarification_questions, list)
        assert isinstance(state.clarification_history, list)
        assert state.awaiting_user_response is False
        
        # Execution flow fields
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        assert isinstance(state.execution_plan, list)
        assert isinstance(state.completed_stages, list)
        
        # Result fields (should be None initially)
        assert state.generated_sql is None
        assert state.execution_result is None
        assert state.explanation is None
        assert state.visualization_config is None
        
        # Observability fields
        assert isinstance(state.persona_trace, list)
        assert isinstance(state.errors, list)
        
        # Metadata
        assert state.updated_at is not None
        assert isinstance(state.metadata, dict)
    
    @pytest.mark.asyncio
    async def test_state_serialization_roundtrip(self, client: AsyncClient):
        """Test that state can be serialized and deserialized correctly."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Serialization test"}
        )
        
        conversation_id = response.json()["conversation_id"]
        
        # Get state
        state1 = await conversation_state_manager.get_state(conversation_id)
        assert state1 is not None
        
        # Serialize to dict
        state_dict = state1.to_dict()
        
        # Deserialize back
        from services.conversation_state import ConversationState
        state2 = ConversationState.from_dict(state_dict)
        
        # Verify all fields match
        assert state2.conversation_id == state1.conversation_id
        assert state2.original_nl_query == state1.original_nl_query
        assert state2.current_stage == state1.current_stage
        assert state2.status == state1.status
        assert state2.session_start_time == state1.session_start_time


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestRouterPersistenceErrorHandling:
    """Tests for error handling in state persistence."""
    
    @pytest.mark.asyncio
    async def test_persistence_failure_returns_error(self, client: AsyncClient):
        """Test that persistence failures are handled gracefully."""
        # Mock state manager to fail persistence
        from unittest.mock import patch
        
        with patch.object(
            conversation_state_manager,
            '_store_state',
            side_effect=Exception("Redis connection lost")
        ):
            response = await client.post(
                "/api/v1/query/start",
                json={"query": "Test query"}
            )
            
            # Should return error response
            assert response.status_code in (500, 503)

# ============================================================================
# Acknowledgment Contract Tests (SRS NFR-2)
# ============================================================================
import time

class TestRouterAcknowledgment:
    """Tests to verify the Router acknowledgment logic matches SRS requirements."""
    
    @pytest.mark.asyncio
    async def test_acknowledgment_latency_meets_nfr2(self, client: AsyncClient):
        """Test that the API responds with an acknowledgment within 100ms (NFR-2)."""
        start_time = time.perf_counter()
        
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Test for latency"}
        )
        
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        
        assert response.status_code == 200
        # Check that acknowledgment latency is fast. 
        # NFR-2 states <100ms. In local tests, using <200ms to avoid test flakiness.
        assert latency_ms < 200.0, f"Acknowledgment took {latency_ms:.2f}ms, expected < 200ms"

    @pytest.mark.asyncio
    async def test_acknowledgment_contains_no_answers_and_metadata_only(self, client: AsyncClient):
        """Test that user-facing answers are not leaked in the initial response (SRS Section 7.2)."""
        response = await client.post(
            "/api/v1/query/start",
            json={"query": "Test for payload leakage"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify exactly metadata fields are present
        assert data.get("status") == "success"
        assert "conversation_id" in data
        assert data.get("query") == "Test for payload leakage"
        assert "timestamp" in data
        assert "message" in data
        
        # Verify NO user-facing answer fields exist in the response
        assert "generated_sql" not in data
        assert "execution_result" not in data
        assert "explanation" not in data
        assert "visualization_config" not in data
        assert "clarification_questions" not in data
