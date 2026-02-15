"""
Conversation State Management Service

Provides persistent storage for conversation state using Redis.
Supports both Redis-backed and in-memory fallback modes.

Features:
- Redis-backed persistence (survives restarts, shared across instances)
- In-memory fallback for development/testing
- Automatic TTL/expiration for conversations
- Connection handling with timeouts and error logging
- Credential masking in logs
- Interface compatibility with existing code
"""

import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = Exception
    RedisConnectionError = Exception

from config import settings


logger = logging.getLogger(__name__)


class ConversationState:
    """
    Represents the state of a single conversation.
    
    Attributes:
        conversation_id: Unique conversation identifier (UUID v4)
        created_at: ISO 8601 timestamp of conversation creation
        updated_at: ISO 8601 timestamp of last update
        metadata: Optional metadata dictionary (user context, etc.)
    """
    
    def __init__(
        self,
        conversation_id: str,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize conversation state.
        
        Args:
            conversation_id: UUID v4 conversation ID
            created_at: ISO 8601 creation timestamp (auto-generated if None)
            updated_at: ISO 8601 update timestamp (auto-generated if None)
            metadata: Optional metadata dictionary
        """
        self.conversation_id = conversation_id
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'conversation_id': self.conversation_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """Create from dictionary."""
        return cls(
            conversation_id=data['conversation_id'],
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            metadata=data.get('metadata', {})
        )
    
    def __repr__(self) -> str:
        return f"ConversationState(id={self.conversation_id}, created={self.created_at})"


class ConversationStateManager:
    """
    Manages conversation state with Redis backend and in-memory fallback.
    
    This class provides a unified interface for conversation state management
    that can use either Redis (for production) or in-memory storage (for
    development/testing).
    
    Features:
    - Thread-safe operations
    - Automatic TTL for conversation expiration
    - Connection pooling and error handling
    - Graceful fallback to in-memory mode
    - Credential masking in logs
    
    Usage:
        manager = ConversationStateManager()
        await manager.initialize()
        
        # Get or create conversation
        conv_id = await manager.get_or_create("optional-id")
        
        # Update state
        await manager.upsert_state(conv_id, metadata={"user": "john"})
        
        # Get state
        state = await manager.get_state(conv_id)
        
        # Clear conversation
        await manager.clear(conv_id)
        
        # Cleanup
        await manager.close()
    """
    
    def __init__(self):
        """Initialize the conversation state manager."""
        self._redis_client: Optional[redis.Redis] = None
        self._in_memory_store: Dict[str, ConversationState] = {}
        self._initialized = False
        self._use_redis = settings.redis_enabled and REDIS_AVAILABLE
        self._redis_url: Optional[str] = None
        
        if settings.redis_enabled and not REDIS_AVAILABLE:
            logger.warning(
                "Redis is enabled in config but redis package is not installed. "
                "Falling back to in-memory storage. Install with: pip install redis"
            )
    
    async def initialize(self) -> None:
        """
        Initialize the state manager and establish connections.
        
        Call this once during application startup (in lifespan context).
        Creates Redis client lazily bound to the current event loop.
        """
        if self._initialized:
            logger.warning("ConversationStateManager already initialized")
            return
        
        if self._use_redis:
            # Build Redis connection URL
            password_part = f":{settings.redis_password}@" if settings.redis_password else ""
            protocol = "rediss" if settings.redis_ssl else "redis"
            self._redis_url = (
                f"{protocol}://{password_part}{settings.redis_host}:"
                f"{settings.redis_port}/{settings.redis_db}"
            )
            
            # Create Redis client lazily to bind to current event loop
            await self._ensure_redis_client()
        
        if not self._use_redis:
            logger.warning(
                "Using in-memory conversation state storage. "
                "State will be lost on restart and not shared across instances."
            )
        
        self._initialized = True
    
    async def _ensure_redis_client(self) -> None:
        """
        Ensure Redis client exists and is bound to the current event loop.
        Creates a new client if needed.
        """
        if not self._use_redis or not self._redis_url:
            return
        
        # If client doesn't exist, create it
        if self._redis_client is None:
            try:
                # Create Redis client bound to current event loop
                self._redis_client = redis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=settings.redis_timeout,
                    socket_connect_timeout=settings.redis_timeout,
                    health_check_interval=30,
                )
                
                # Test connection
                await self._redis_client.ping()
                
                # Mask password in logs
                safe_url = self._redis_url.replace(settings.redis_password or "", "***") if settings.redis_password else self._redis_url
                logger.info(f"Connected to Redis: {safe_url}")
                logger.info(f"Conversation TTL: {settings.conversation_state_ttl}s")
                
            except (RedisConnectionError, RedisError) as e:
                logger.error(
                    f"Failed to connect to Redis: {e.__class__.__name__}: {str(e)}. "
                    f"Falling back to in-memory storage."
                )
                self._redis_client = None
                self._use_redis = False
            except Exception as e:
                logger.error(
                    f"Unexpected error initializing Redis: {e.__class__.__name__}: {str(e)}. "
                    f"Falling back to in-memory storage."
                )
                self._redis_client = None
                self._use_redis = False
    
    async def close(self) -> None:
        """
        Close connections and cleanup resources.
        
        Call this during application shutdown (in lifespan context).
        Resets Redis client to None to allow recreation in new event loop.
        """
        if self._redis_client:
            try:
                await self._redis_client.aclose()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self._redis_client = None
        
        self._in_memory_store.clear()
        self._initialized = False
    
    def _generate_conversation_id(self) -> str:
        """Generate a new UUID v4 conversation ID."""
        return str(uuid.uuid4())
    
    def _get_redis_key(self, conversation_id: str) -> str:
        """Get Redis key for conversation ID."""
        return f"conversation:{conversation_id}"
    
    async def get_or_create(self, conversation_id: Optional[str] = None) -> str:
        """
        Get existing conversation or create a new one.
        
        Args:
            conversation_id: Optional conversation ID. If None, creates new conversation.
        
        Returns:
            Conversation ID (existing or newly created)
        """
        # If ID provided, check if it exists
        if conversation_id:
            state = await self.get_state(conversation_id)
            if state:
                return conversation_id
        
        # Generate new conversation ID
        new_id = conversation_id or self._generate_conversation_id()
        
        # Create initial state
        state = ConversationState(conversation_id=new_id)
        
        # Store it
        await self._store_state(state)
        
        logger.info(f"Created new conversation: {new_id}")
        return new_id
    
    async def upsert_state(
        self,
        conversation_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update or insert conversation state.
        
        Args:
            conversation_id: Conversation ID to update
            metadata: Optional metadata to merge with existing
        """
        # Get existing state or create new
        existing = await self.get_state(conversation_id)
        
        if existing:
            # Update existing state
            if metadata:
                existing.metadata.update(metadata)
            existing.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            await self._store_state(existing)
        else:
            # Create new state
            state = ConversationState(
                conversation_id=conversation_id,
                metadata=metadata
            )
            await self._store_state(state)
    
    async def get_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Get conversation state by ID.
        
        Args:
            conversation_id: Conversation ID to retrieve
        
        Returns:
            ConversationState if found, None otherwise
        """
        if self._use_redis:
            await self._ensure_redis_client()
            
        if self._use_redis and self._redis_client:
            try:
                key = self._get_redis_key(conversation_id)
                data = await self._redis_client.get(key)
                
                if data:
                    state_dict = json.loads(data)
                    return ConversationState.from_dict(state_dict)
                
                return None
            
            except (RedisError, json.JSONDecodeError) as e:
                logger.error(
                    f"Error retrieving conversation {conversation_id} from Redis: {e}. "
                    f"Falling back to in-memory."
                )
                # Fallback to in-memory
                return self._in_memory_store.get(conversation_id)
        
        else:
            # Use in-memory storage
            return self._in_memory_store.get(conversation_id)
    
    async def _store_state(self, state: ConversationState) -> None:
        """
        Store conversation state (internal method).
        
        Args:
            state: ConversationState to store
        """
        if self._use_redis:
            await self._ensure_redis_client()
            
        if self._use_redis and self._redis_client:
            try:
                key = self._get_redis_key(state.conversation_id)
                data = json.dumps(state.to_dict())
                
                # Set with TTL if configured
                if settings.conversation_state_ttl > 0:
                    await self._redis_client.setex(
                        key,
                        settings.conversation_state_ttl,
                        data
                    )
                else:
                    await self._redis_client.set(key, data)
            
            except RedisError as e:
                logger.error(
                    f"Error storing conversation {state.conversation_id} in Redis: {e}. "
                    f"Falling back to in-memory."
                )
                # Fallback to in-memory
                self._in_memory_store[state.conversation_id] = state
        
        else:
            # Use in-memory storage
            self._in_memory_store[state.conversation_id] = state
    
    async def clear(self, conversation_id: str) -> bool:
        """
        Clear conversation state.
        
        Args:
            conversation_id: Conversation ID to clear
        
        Returns:
            True if conversation existed and was cleared, False otherwise
        """
        if self._use_redis:
            await self._ensure_redis_client()
            
        if self._use_redis and self._redis_client:
            try:
                key = self._get_redis_key(conversation_id)
                result = await self._redis_client.delete(key)
                return result > 0
            
            except RedisError as e:
                logger.error(
                    f"Error clearing conversation {conversation_id} from Redis: {e}. "
                    f"Falling back to in-memory."
                )
                # Fallback to in-memory
                if conversation_id in self._in_memory_store:
                    del self._in_memory_store[conversation_id]
                    return True
                return False
        
        else:
            # Use in-memory storage
            if conversation_id in self._in_memory_store:
                del self._in_memory_store[conversation_id]
                return True
            return False
    
    async def clear_all(self) -> int:
        """
        Clear all conversation state (use with caution).
        
        Returns:
            Number of conversations cleared
        """
        if self._use_redis:
            await self._ensure_redis_client()
            
        if self._use_redis and self._redis_client:
            try:
                # Find all conversation keys
                pattern = self._get_redis_key("*")
                keys = []
                async for key in self._redis_client.scan_iter(match=pattern):
                    keys.append(key)
                
                if keys:
                    deleted = await self._redis_client.delete(*keys)
                    logger.warning(f"Cleared {deleted} conversations from Redis")
                    return deleted
                
                return 0
            
            except RedisError as e:
                logger.error(f"Error clearing all conversations from Redis: {e}")
                return 0
        
        else:
            # Use in-memory storage
            count = len(self._in_memory_store)
            self._in_memory_store.clear()
            logger.warning(f"Cleared {count} conversations from in-memory storage")
            return count
    
    @property
    def is_redis_enabled(self) -> bool:
        """Check if Redis backend is enabled and connected."""
        return self._use_redis and self._redis_client is not None
    
    @property
    def storage_mode(self) -> str:
        """Get current storage mode ('redis' or 'memory')."""
        return "redis" if self.is_redis_enabled else "memory"


# Singleton instance - initialize in application lifespan
conversation_state_manager = ConversationStateManager()
