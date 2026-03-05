"""
Unit Tests for Router Service

Tests the RouterService initialization and state creation logic.

Test Coverage:
- Conversation state initialization
- Stage and status setting
- Persistence error handling
- Retry logic
- Metadata storage
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from typing import Any

from services.router_service import RouterService
from services.conversation_state import ConversationStateManager, ConversationState
from schemas.conversation import ExecutionStage, ConversationStatus


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_state_manager() -> Any:
    """Provide a mocked ConversationStateManager."""
    manager = AsyncMock(spec=ConversationStateManager)
    manager.generate_conversation_id.return_value = "test-conv-id-123"
    manager._store_state = AsyncMock()
    manager.get_state = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def router_service(mock_state_manager: Any) -> RouterService:
    """Provide a RouterService instance with mocked dependencies."""
    return RouterService(mock_state_manager)


# ============================================================================
# RouterService Initialization Tests
# ============================================================================

class TestRouterServiceInitialization:
    """Tests for RouterService.initialize_conversation()."""
    
    @pytest.mark.asyncio
    async def test_initialize_new_conversation(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test initializing a new conversation without providing conversation_id."""
        query = "Show me sales from last month"
        user_context = {"user_id": "user-123", "session_id": "session-abc"}
        correlation_id = "corr-xyz-789"
        
        state = await router_service.initialize_conversation(
            query=query,
            user_context=user_context,
            correlation_id=correlation_id,
        )
        
        # Verify state fields
        assert state.conversation_id == "test-conv-id-123"
        assert state.original_nl_query == query
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        assert state.awaiting_user_response is False
        assert state.metadata['user_context'] == user_context
        assert state.metadata['correlation_id'] == correlation_id
        
        # Verify persistence was called
        mock_state_manager._store_state.assert_called_once()
        stored_state = mock_state_manager._store_state.call_args[0][0]
        assert stored_state.conversation_id == "test-conv-id-123"
    
    @pytest.mark.asyncio
    async def test_initialize_with_provided_conversation_id(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test initializing a conversation with a provided conversation_id."""
        query = "Count active users"
        conv_id = "provided-conv-id-456"
        
        state = await router_service.initialize_conversation(
            query=query,
            conversation_id=conv_id,
        )
        
        # Verify conversation_id was used
        assert state.conversation_id == conv_id
        assert state.original_nl_query == query
        
        # Verify generate_conversation_id was NOT called
        mock_state_manager.generate_conversation_id.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_initialize_without_user_context(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test initialization without user context (metadata should be empty dict)."""
        query = "Show revenue"
        
        state = await router_service.initialize_conversation(query=query)
        
        # Verify metadata has empty user_context
        assert state.metadata['user_context'] == {}
        assert state.metadata['correlation_id'] is None
    
    @pytest.mark.asyncio
    async def test_initialize_sets_correct_timestamps(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test that timestamps are set correctly."""
        query = "Test query"
        
        # Mock datetime to control timestamp
        with patch('services.conversation_state.datetime') as mock_datetime:
            mock_now = datetime(2026, 3, 5, 10, 30, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone
            
            state = await router_service.initialize_conversation(query=query)
            
            # Verify timestamps are set
            assert state.session_start_time is not None
            assert state.updated_at is not None


# ============================================================================
# Error Handling and Retry Tests
# ============================================================================

class TestRouterServiceErrorHandling:
    """Tests for error handling and retry logic."""
    
    @pytest.mark.asyncio
    async def test_persist_with_retry_success_on_first_attempt(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test successful persistence on first attempt."""
        state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query"
        )
        
        await router_service._persist_state_with_retry(state)  # type: ignore[reportPrivateUsage]
        
        # Verify _store_state was called once
        assert mock_state_manager._store_state.call_count == 1
    
    @pytest.mark.asyncio
    async def test_persist_with_retry_success_on_second_attempt(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test successful persistence after one retry."""
        state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query"
        )
        
        # First call fails, second succeeds
        mock_state_manager._store_state.side_effect = [
            Exception("Connection failed"),
            None  # Success on second attempt
        ]
        
        await router_service._persist_state_with_retry(state, max_retries=2)  # type: ignore[reportPrivateUsage]
        
        # Verify _store_state was called twice
        assert mock_state_manager._store_state.call_count == 2
    
    @pytest.mark.asyncio
    async def test_persist_with_retry_all_attempts_fail(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test that exception is raised when all retry attempts fail."""
        state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query"
        )
        
        # All attempts fail
        mock_state_manager._store_state.side_effect = Exception("Persistent failure")
        
        with pytest.raises(Exception, match="Failed to persist conversation state after"):
            await router_service._persist_state_with_retry(state, max_retries=2)  # type: ignore[reportPrivateUsage]
        
        # Verify _store_state was called 3 times (initial + 2 retries)
        assert mock_state_manager._store_state.call_count == 3
    
    @pytest.mark.asyncio
    async def test_initialize_conversation_propagates_persistence_error(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test that initialization propagates persistence errors."""
        query = "Test query"
        
        # Make persistence fail
        mock_state_manager._store_state.side_effect = Exception("Redis connection lost")
        
        with pytest.raises(Exception, match="Failed to persist conversation state"):
            await router_service.initialize_conversation(query=query)


# ============================================================================
# Stage Update Tests
# ============================================================================

class TestRouterServiceStageUpdate:
    """Tests for RouterService.update_conversation_stage()."""
    
    @pytest.mark.asyncio
    async def test_update_stage_success(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test updating conversation stage."""
        # Create existing state
        existing_state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query",
            current_stage=ExecutionStage.PLANNING,
            status=ConversationStatus.PROCESSING,
        )
        mock_state_manager.get_state.return_value = existing_state
        
        # Update stage
        await router_service.update_conversation_stage(
            conversation_id="test-id",
            stage=ExecutionStage.SCHEMA_RETRIEVAL,
            status=ConversationStatus.PROCESSING,
        )
        
        # Verify state was updated
        assert existing_state.current_stage == ExecutionStage.SCHEMA_RETRIEVAL
        assert existing_state.status == ConversationStatus.PROCESSING
        
        # Verify persistence was called
        mock_state_manager._store_state.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_stage_with_additional_fields(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test updating stage with additional fields."""
        existing_state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query",
        )
        mock_state_manager.get_state.return_value = existing_state
        
        # Update with execution_plan
        await router_service.update_conversation_stage(
            conversation_id="test-id",
            stage=ExecutionStage.SCHEMA_RETRIEVAL,
            execution_plan=["SchemaExpert", "SQLWriter"],
        )
        
        # Verify additional fields were updated
        assert existing_state.execution_plan == ["SchemaExpert", "SQLWriter"]
    
    @pytest.mark.asyncio
    async def test_update_stage_conversation_not_found(self, router_service: RouterService, mock_state_manager: Any) -> None:
        """Test updating stage when conversation doesn't exist."""
        mock_state_manager.get_state.return_value = None
        
        # Should not raise error, just log warning
        await router_service.update_conversation_stage(
            conversation_id="non-existent-id",
            stage=ExecutionStage.SCHEMA_RETRIEVAL,
        )
        
        # Verify persistence was not called
        mock_state_manager._store_state.assert_not_called()


# ============================================================================
# State Field Validation Tests
# ============================================================================

class TestConversationStateFields:
    """Tests to verify ConversationState has all required SRS fields."""
    
    def test_conversation_state_has_all_srs_fields(self) -> None:
        """Verify ConversationState has all 18 required SRS fields."""
        state = ConversationState(conversation_id="test-id")
        
        # Core identity fields
        assert hasattr(state, 'conversation_id')
        assert hasattr(state, 'session_start_time')
        
        # Query fields
        assert hasattr(state, 'original_nl_query')
        assert hasattr(state, 'current_nl_query')
        
        # Parameter resolution
        assert hasattr(state, 'resolved_parameters')
        
        # Clarification fields
        assert hasattr(state, 'pending_clarification_questions')
        assert hasattr(state, 'clarification_history')
        assert hasattr(state, 'awaiting_user_response')
        
        # Execution flow fields
        assert hasattr(state, 'current_stage')
        assert hasattr(state, 'status')
        assert hasattr(state, 'execution_plan')
        assert hasattr(state, 'completed_stages')
        
        # Result fields
        assert hasattr(state, 'generated_sql')
        assert hasattr(state, 'execution_result')
        assert hasattr(state, 'explanation')
        assert hasattr(state, 'visualization_config')
        
        # Observability fields
        assert hasattr(state, 'persona_trace')
        assert hasattr(state, 'errors')
        
        # Metadata
        assert hasattr(state, 'updated_at')
        assert hasattr(state, 'metadata')
    
    def test_conversation_state_default_values(self) -> None:
        """Test that ConversationState initializes with correct defaults."""
        state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Test query"
        )
        
        # Verify defaults
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        assert state.awaiting_user_response is False
        assert state.resolved_parameters == {}
        assert state.pending_clarification_questions == []
        assert state.clarification_history == []
        assert state.execution_plan == []
        assert state.completed_stages == []
        assert state.persona_trace == []
        assert state.errors == []
        assert state.metadata == {}
    
    def test_conversation_state_serialization(self) -> None:
        """Test that ConversationState can be serialized to dict."""
        state = ConversationState(
            conversation_id="test-id",
            original_nl_query="Show sales",
            current_stage=ExecutionStage.PLANNING,
            status=ConversationStatus.PROCESSING,
            metadata={"key": "value"}
        )
        
        state_dict = state.to_dict()
        
        # Verify all fields are in dict
        assert 'conversation_id' in state_dict
        assert 'session_start_time' in state_dict
        assert 'original_nl_query' in state_dict
        assert 'current_stage' in state_dict
        assert 'status' in state_dict
        assert 'metadata' in state_dict
        
        # Verify enums are serialized as strings
        assert state_dict['current_stage'] == 'planning'
        assert state_dict['status'] == 'processing'
    
    def test_conversation_state_deserialization(self) -> None:
        """Test that ConversationState can be deserialized from dict."""
        from typing import Dict, Any as AnyType
        
        state_dict: Dict[str, AnyType] = {
            'conversation_id': 'test-id',
            'session_start_time': '2026-03-05T10:30:00Z',
            'original_nl_query': 'Show sales',
            'current_stage': 'planning',
            'status': 'processing',
            'updated_at': '2026-03-05T10:31:00Z',
            'metadata': {'key': 'value'},
        }
        
        state = ConversationState.from_dict(state_dict)
        
        # Verify fields
        assert state.conversation_id == 'test-id'
        assert state.original_nl_query == 'Show sales'
        assert state.current_stage == ExecutionStage.PLANNING
        assert state.status == ConversationStatus.PROCESSING
        assert state.metadata == {'key': 'value'}
