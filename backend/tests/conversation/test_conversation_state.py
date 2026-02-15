"""
Integration Tests for Conversation State Management

Tests the Redis-backed conversation state manager and in-memory fallback.

Test Coverage:
- Redis mode operations (requires Redis running)
- In-memory fallback mode
- TTL/expiration behavior
- Error handling and resilience
- State persistence across restarts (Redis only)
- Multi-instance sharing (Redis only)
"""

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from typing import Dict, Any

from services.conversation_state import (
    ConversationState,
    ConversationStateManager,
    conversation_state_manager
)
from config import settings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def clean_manager():
    """Provide a clean conversation state manager for each test."""
    manager = ConversationStateManager()
    # Ensure clean state before initialization
    await manager.close()
    await manager.initialize()
    
    yield manager
    
    # Cleanup: Clear all conversations
    await manager.clear_all()
    await manager.close()


@pytest.fixture
async def redis_manager():
    """
    Provide a Redis-enabled manager (skips if Redis not available).
    
    This fixture requires a running Redis instance on localhost:6379.
    Tests using this fixture will be skipped if Redis is not available.
    """
    # Check if Redis is available
    if not settings.redis_enabled:
        pytest.skip("Redis is disabled in configuration")
    
    manager = ConversationStateManager()
    # Ensure clean state before initialization
    await manager.close()
    await manager.initialize()
    
    if not manager.is_redis_enabled:
        pytest.skip("Redis is not available - check if Redis server is running")
    
    yield manager
    
    # Cleanup: Clear all conversations
    await manager.clear_all()
    await manager.close()


@pytest.fixture
async def memory_manager():
    """Provide an in-memory only manager."""
    # Temporarily disable Redis
    original_redis_enabled = settings.redis_enabled
    settings.redis_enabled = False
    
    manager = ConversationStateManager()
    # Ensure clean state before initialization
    await manager.close()
    await manager.initialize()
    
    yield manager
    
    await manager.clear_all()
    await manager.close()
    
    # Restore Redis setting
    settings.redis_enabled = original_redis_enabled


# ============================================================================
# ConversationState Tests
# ============================================================================

class TestConversationState:
    """Tests for ConversationState data model."""
    
    def test_conversation_state_creation(self):
        """Test creating a conversation state with defaults."""
        conv_id = "test-id-123"
        state = ConversationState(conversation_id=conv_id)
        
        assert state.conversation_id == conv_id
        assert state.created_at is not None
        assert state.updated_at is not None
        assert state.metadata == {}
    
    def test_conversation_state_with_metadata(self):
        """Test creating a conversation state with metadata."""
        conv_id = "test-id-456"
        metadata = {"user": "john", "session": "abc"}
        state = ConversationState(conversation_id=conv_id, metadata=metadata)
        
        assert state.conversation_id == conv_id
        assert state.metadata == metadata
    
    def test_conversation_state_to_dict(self):
        """Test serialization to dictionary."""
        conv_id = "test-id-789"
        metadata = {"key": "value"}
        state = ConversationState(conversation_id=conv_id, metadata=metadata)
        
        data = state.to_dict()
        
        assert data['conversation_id'] == conv_id
        assert data['metadata'] == metadata
        assert 'created_at' in data
        assert 'updated_at' in data
    
    def test_conversation_state_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            'conversation_id': 'test-id-abc',
            'created_at': '2024-01-01T12:00:00Z',
            'updated_at': '2024-01-01T12:30:00Z',
            'metadata': {'user': 'jane'}
        }
        
        state = ConversationState.from_dict(data)
        
        assert state.conversation_id == data['conversation_id']
        assert state.created_at == data['created_at']
        assert state.updated_at == data['updated_at']
        assert state.metadata == data['metadata']
    
    def test_conversation_state_repr(self):
        """Test string representation."""
        conv_id = "test-id-repr"
        state = ConversationState(conversation_id=conv_id)
        
        repr_str = repr(state)
        
        assert conv_id in repr_str
        assert "ConversationState" in repr_str


# ============================================================================
# ConversationStateManager Basic Operations
# ============================================================================

class TestConversationStateManagerBasics:
    """Tests for basic manager operations (works with both Redis and in-memory)."""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, clean_manager):
        """Test manager initializes successfully."""
        assert clean_manager._initialized
        assert clean_manager.storage_mode in ['redis', 'memory']
    
    @pytest.mark.asyncio
    async def test_get_or_create_new_conversation(self, clean_manager):
        """Test creating a new conversation without providing ID."""
        conv_id = await clean_manager.get_or_create()
        
        assert conv_id is not None
        assert len(conv_id) == 36  # UUID v4 format
        
        # Verify it was stored
        state = await clean_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id
    
    @pytest.mark.asyncio
    async def test_get_or_create_existing_conversation(self, clean_manager):
        """Test getting an existing conversation."""
        # Create first
        conv_id = await clean_manager.get_or_create()
        
        # Get the same one
        same_id = await clean_manager.get_or_create(conv_id)
        
        assert same_id == conv_id
    
    @pytest.mark.asyncio
    async def test_get_or_create_with_provided_id(self, clean_manager):
        """Test creating conversation with specific ID."""
        custom_id = "custom-conversation-id"
        conv_id = await clean_manager.get_or_create(custom_id)
        
        assert conv_id == custom_id
        
        # Verify it was stored
        state = await clean_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == custom_id
    
    @pytest.mark.asyncio
    async def test_upsert_state_new(self, clean_manager):
        """Test upserting state for a new conversation."""
        conv_id = "new-conversation"
        metadata = {"user": "alice", "session": "xyz"}
        
        await clean_manager.upsert_state(conv_id, metadata=metadata)
        
        state = await clean_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id
        assert state.metadata == metadata
    
    @pytest.mark.asyncio
    async def test_upsert_state_existing(self, clean_manager):
        """Test upserting state for an existing conversation."""
        # Create initial state
        conv_id = await clean_manager.get_or_create()
        await clean_manager.upsert_state(conv_id, metadata={"key1": "value1"})
        
        # Update state
        await asyncio.sleep(0.01)  # Ensure timestamp differs
        await clean_manager.upsert_state(conv_id, metadata={"key2": "value2"})
        
        state = await clean_manager.get_state(conv_id)
        assert state is not None
        assert state.metadata == {"key1": "value1", "key2": "value2"}  # Merged
        assert state.updated_at > state.created_at
    
    @pytest.mark.asyncio
    async def test_get_state_nonexistent(self, clean_manager):
        """Test getting state for non-existent conversation."""
        state = await clean_manager.get_state("nonexistent-id")
        assert state is None
    
    @pytest.mark.asyncio
    async def test_clear_conversation(self, clean_manager):
        """Test clearing a conversation."""
        conv_id = await clean_manager.get_or_create()
        
        # Verify it exists
        state = await clean_manager.get_state(conv_id)
        assert state is not None
        
        # Clear it
        result = await clean_manager.clear(conv_id)
        assert result is True
        
        # Verify it's gone
        state = await clean_manager.get_state(conv_id)
        assert state is None
    
    @pytest.mark.asyncio
    async def test_clear_nonexistent_conversation(self, clean_manager):
        """Test clearing a conversation that doesn't exist."""
        result = await clean_manager.clear("nonexistent-id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_clear_all_conversations(self, clean_manager):
        """Test clearing all conversations."""
        # Create multiple conversations
        conv_ids = []
        for _ in range(5):
            conv_id = await clean_manager.get_or_create()
            conv_ids.append(conv_id)
        
        # Verify they exist
        for conv_id in conv_ids:
            state = await clean_manager.get_state(conv_id)
            assert state is not None
        
        # Clear all
        count = await clean_manager.clear_all()
        assert count >= 5  # May be more if other tests left data
        
        # Verify they're gone
        for conv_id in conv_ids:
            state = await clean_manager.get_state(conv_id)
            assert state is None


# ============================================================================
# Redis-Specific Tests
# ============================================================================

class TestRedisMode:
    """Tests specific to Redis backend."""
    
    @pytest.mark.asyncio
    async def test_redis_storage_mode(self, redis_manager):
        """Test that Redis mode is correctly identified."""
        assert redis_manager.storage_mode == "redis"
        assert redis_manager.is_redis_enabled
    
    @pytest.mark.asyncio
    async def test_redis_persistence(self, redis_manager):
        """Test that data persists in Redis."""
        conv_id = await redis_manager.get_or_create()
        metadata = {"persistent": "data"}
        await redis_manager.upsert_state(conv_id, metadata=metadata)
        
        # Create a new manager instance (simulates restart)
        new_manager = ConversationStateManager()
        await new_manager.initialize()
        
        # Data should still exist
        state = await new_manager.get_state(conv_id)
        assert state is not None
        assert state.conversation_id == conv_id
        assert state.metadata == metadata
        
        await new_manager.close()
    
    @pytest.mark.asyncio
    async def test_redis_key_format(self, redis_manager):
        """Test Redis key format."""
        conv_id = "test-key-format"
        expected_key = f"conversation:{conv_id}"
        
        actual_key = redis_manager._get_redis_key(conv_id)
        assert actual_key == expected_key
    
    @pytest.mark.asyncio
    async def test_redis_ttl_set(self, redis_manager):
        """Test that TTL is set on Redis keys."""
        # Skip if TTL is disabled
        if settings.conversation_state_ttl == 0:
            pytest.skip("TTL is disabled (set to 0)")
        
        conv_id = await redis_manager.get_or_create()
        
        # Check TTL in Redis
        key = redis_manager._get_redis_key(conv_id)
        ttl = await redis_manager._redis_client.ttl(key)
        
        # TTL should be set and close to the configured value
        assert ttl > 0
        assert ttl <= settings.conversation_state_ttl


# ============================================================================
# In-Memory Fallback Tests
# ============================================================================

class TestMemoryMode:
    """Tests for in-memory fallback mode."""
    
    @pytest.mark.asyncio
    async def test_memory_storage_mode(self, memory_manager):
        """Test that memory mode is correctly identified."""
        assert memory_manager.storage_mode == "memory"
        assert not memory_manager.is_redis_enabled
    
    @pytest.mark.asyncio
    async def test_memory_basic_operations(self, memory_manager):
        """Test basic operations work in memory mode."""
        conv_id = await memory_manager.get_or_create()
        metadata = {"memory": "data"}
        await memory_manager.upsert_state(conv_id, metadata=metadata)
        
        state = await memory_manager.get_state(conv_id)
        assert state is not None
        assert state.metadata == metadata
    
    @pytest.mark.asyncio
    async def test_memory_no_persistence(self, memory_manager):
        """Test that data doesn't persist across manager instances."""
        conv_id = await memory_manager.get_or_create()
        
        # Create a new manager (simulates restart)
        new_manager = ConversationStateManager()
        settings.redis_enabled = False
        await new_manager.initialize()
        
        # Data should not exist
        state = await new_manager.get_state(conv_id)
        assert state is None
        
        await new_manager.close()
        settings.redis_enabled = True  # Restore


# ============================================================================
# Error Handling and Resilience Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling and resilience."""
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure_fallback(self):
        """Test fallback to memory when Redis connection fails."""
        # Mock Redis to fail
        with patch('services.conversation_state.redis') as mock_redis:
            mock_redis.from_url = MagicMock(side_effect=Exception("Connection failed"))
            
            manager = ConversationStateManager()
            await manager.initialize()
            
            # Should fall back to memory
            assert manager.storage_mode == "memory"
            
            # Should still work
            conv_id = await manager.get_or_create()
            assert conv_id is not None
            
            await manager.close()
    
    @pytest.mark.asyncio
    async def test_double_initialization_warning(self, clean_manager, caplog):
        """Test that double initialization logs a warning."""
        # Initialize again
        await clean_manager.initialize()
        
        # Check for warning log
        assert any("already initialized" in record.message.lower() 
                  for record in caplog.records)
    
    @pytest.mark.asyncio
    async def test_close_without_redis(self, memory_manager):
        """Test closing manager in memory mode doesn't error."""
        await memory_manager.close()  # Should not raise


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests with query endpoint simulation."""
    
    @pytest.mark.asyncio
    async def test_query_workflow(self, clean_manager):
        """Test typical query workflow with conversation state."""
        # First query - no conversation ID provided
        conv_id = await clean_manager.get_or_create()
        await clean_manager.upsert_state(
            conv_id,
            metadata={'user_context': {'user_id': '123'}}
        )
        
        # Second query - with conversation ID
        same_id = await clean_manager.get_or_create(conv_id)
        assert same_id == conv_id
        
        # Update with more metadata
        await clean_manager.upsert_state(
            conv_id,
            metadata={'query_count': 2}
        )
        
        # Verify final state
        state = await clean_manager.get_state(conv_id)
        assert state.metadata['user_context'] == {'user_id': '123'}
        assert state.metadata['query_count'] == 2
    
    @pytest.mark.asyncio
    async def test_concurrent_conversations(self, clean_manager):
        """Test handling multiple concurrent conversations."""
        # Create multiple conversations concurrently
        tasks = [clean_manager.get_or_create() for _ in range(10)]
        conv_ids = await asyncio.gather(*tasks)
        
        # All should be unique
        assert len(conv_ids) == len(set(conv_ids))
        
        # All should exist
        for conv_id in conv_ids:
            state = await clean_manager.get_state(conv_id)
            assert state is not None


# ============================================================================
# Singleton Tests
# ============================================================================

class TestSingleton:
    """Tests for the singleton conversation_state_manager."""
    
    @pytest.mark.asyncio
    async def test_singleton_available(self):
        """Test that the singleton instance is available."""
        assert conversation_state_manager is not None
    
    @pytest.mark.asyncio
    async def test_singleton_can_initialize(self):
        """Test that singleton can be initialized."""
        # Note: In real app, this is done in main.py lifespan
        # Here we just verify it doesn't error
        await conversation_state_manager.initialize()
        assert conversation_state_manager._initialized
