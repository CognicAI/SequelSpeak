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
- SRS v2 Section 6.1 compliant state structure
"""

import logging
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    RedisError = Exception  # type: ignore
    RedisConnectionError = Exception  # type: ignore
    REDIS_AVAILABLE = False  # type: ignore[assignment]

if TYPE_CHECKING:
    from redis.asyncio import Redis

from config import settings
from schemas.conversation import (
    ExecutionStage,
    ConversationStatus,
)


logger = logging.getLogger(__name__)


class ConversationState:
    """
    Represents the state of a single conversation.
    
    Implements the SRS v2 Section 6.1 ConversationState schema with all 18 required fields.
    
    Design Philosophy:
    - Gradual enhancement: Fields are added incrementally as personas are implemented
    - Backward compatibility: Existing code using only conversation_id/metadata still works
    - Type safety: Uses proper enums for stage and status
    - Observability: Persona trace and error tracking built-in
    
    Attributes:
        conversation_id: Unique conversation identifier (UUID v4)
        session_start_time: ISO 8601 timestamp of conversation creation
        original_nl_query: User's original natural language question
        current_nl_query: Refined query after clarification
        resolved_parameters: Resolved query parameters (time_range, metric, filters)
        pending_clarification_questions: Questions awaiting user response
        clarification_history: Q&A pairs from clarification rounds
        awaiting_user_response: True if execution paused for clarification
        current_stage: Current position in execution pipeline
        status: High-level conversation status
        execution_plan: Ordered persona names to execute
        completed_stages: Personas that finished successfully
        generated_sql: SQLWriter output (validated SQL)
        execution_result: Query results from Executor
        explanation: Explainer output (plain English)
        visualization_config: Analytics persona output
        persona_trace: Log of persona inputs/outputs
        errors: Error records from failed stages
        updated_at: ISO 8601 timestamp of last update
        metadata: Additional metadata (user_context, correlation_id, etc.)
    """
    
    def __init__(
        self,
        conversation_id: str,
        session_start_time: Optional[str] = None,
        original_nl_query: Optional[str] = None,
        current_nl_query: Optional[str] = None,
        resolved_parameters: Optional[Dict[str, Any]] = None,
        pending_clarification_questions: Optional[List[str]] = None,
        clarification_history: Optional[List[Dict[str, Any]]] = None,
        awaiting_user_response: bool = False,
        current_stage: ExecutionStage = ExecutionStage.PLANNING,
        status: ConversationStatus = ConversationStatus.PROCESSING,
        execution_plan: Optional[List[str]] = None,
        completed_stages: Optional[List[str]] = None,
        generated_sql: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        explanation: Optional[str] = None,
        visualization_config: Optional[Dict[str, Any]] = None,
        persona_trace: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        updated_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # Legacy fields for backward compatibility
        created_at: Optional[str] = None,
    ):
        """
        Initialize conversation state.
        
        Args:
            conversation_id: UUID v4 conversation ID
            session_start_time: ISO 8601 creation timestamp (auto-generated if None)
            original_nl_query: User's original query
            current_nl_query: Refined query after clarification
            resolved_parameters: Resolved query parameters
            pending_clarification_questions: Questions awaiting response
            clarification_history: Q&A pairs
            awaiting_user_response: True if paused for clarification
            current_stage: Current execution stage
            status: High-level status
            execution_plan: Ordered persona names
            completed_stages: Finished persona names
            generated_sql: Final validated SQL
            execution_result: Query results
            explanation: Plain English explanation
            visualization_config: Visualization settings
            persona_trace: Persona execution log
            errors: Error records
            updated_at: Last update timestamp (auto-generated if None)
            metadata: Additional metadata
            created_at: Legacy field, maps to session_start_time
        """
        self.conversation_id = conversation_id
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Core identity fields
        self.session_start_time = session_start_time or created_at or now
        
        # Query fields
        self.original_nl_query = original_nl_query
        self.current_nl_query = current_nl_query
        
        # Parameter resolution
        self.resolved_parameters = resolved_parameters or {}
        
        # Clarification fields
        self.pending_clarification_questions = pending_clarification_questions or []
        self.clarification_history = clarification_history or []
        self.awaiting_user_response = awaiting_user_response
        
        # Execution flow fields
        self.current_stage = current_stage
        self.status = status
        self.execution_plan = execution_plan or []
        self.completed_stages = completed_stages or []
        
        # Result fields
        self.generated_sql = generated_sql
        self.execution_result = execution_result
        self.explanation = explanation
        self.visualization_config = visualization_config
        
        # Observability fields
        self.persona_trace = persona_trace or []
        self.errors = errors or []
        
        # Metadata
        self.updated_at = updated_at or now
        self.metadata = metadata or {}
    
    # Legacy property for backward compatibility
    @property
    def created_at(self) -> str:
        """Backward compatibility: created_at maps to session_start_time."""
        return self.session_start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns a dictionary representation of all state fields.
        """
        return {
            # Core identity
            'conversation_id': self.conversation_id,
            'session_start_time': self.session_start_time,
            
            # Query fields
            'original_nl_query': self.original_nl_query,
            'current_nl_query': self.current_nl_query,
            
            # Parameter resolution
            'resolved_parameters': self.resolved_parameters,
            
            # Clarification fields
            'pending_clarification_questions': self.pending_clarification_questions,
            'clarification_history': self.clarification_history,
            'awaiting_user_response': self.awaiting_user_response,
            
            # Execution flow fields
            'current_stage': self.current_stage.value,
            'status': self.status.value,
            'execution_plan': self.execution_plan,
            'completed_stages': self.completed_stages,
            
            # Result fields
            'generated_sql': self.generated_sql,
            'execution_result': self.execution_result,
            'explanation': self.explanation,
            'visualization_config': self.visualization_config,
            
            # Observability fields
            'persona_trace': self.persona_trace,
            'errors': self.errors,
            
            # Metadata
            'updated_at': self.updated_at,
            'metadata': self.metadata,
            
            # Legacy fields for backward compatibility
            'created_at': self.session_start_time,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """
        Create from dictionary.
        
        Handles both new SRS-compliant format and legacy format.
        """
        # Parse enums if present as strings
        current_stage = data.get('current_stage', ExecutionStage.PLANNING)
        if isinstance(current_stage, str):
            try:
                current_stage = ExecutionStage(current_stage)
            except ValueError:
                current_stage = ExecutionStage.PLANNING
        
        status = data.get('status', ConversationStatus.PROCESSING)
        if isinstance(status, str):
            try:
                status = ConversationStatus(status)
            except ValueError:
                status = ConversationStatus.PROCESSING
        
        return cls(
            conversation_id=data['conversation_id'],
            session_start_time=data.get('session_start_time', data.get('created_at')),
            original_nl_query=data.get('original_nl_query'),
            current_nl_query=data.get('current_nl_query'),
            resolved_parameters=data.get('resolved_parameters'),
            pending_clarification_questions=data.get('pending_clarification_questions'),
            clarification_history=data.get('clarification_history'),
            awaiting_user_response=data.get('awaiting_user_response', False),
            current_stage=current_stage,
            status=status,
            execution_plan=data.get('execution_plan'),
            completed_stages=data.get('completed_stages'),
            generated_sql=data.get('generated_sql'),
            execution_result=data.get('execution_result'),
            explanation=data.get('explanation'),
            visualization_config=data.get('visualization_config'),
            persona_trace=data.get('persona_trace'),
            errors=data.get('errors'),
            updated_at=data.get('updated_at'),
            metadata=data.get('metadata', {}),
        )
    
    def __repr__(self) -> str:
        return (
            f"ConversationState(id={self.conversation_id}, "
            f"stage={self.current_stage.value}, "
            f"status={self.status.value})"
        )



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
        self._redis_client: Optional['Redis'] = None
        self._in_memory_store: Dict[str, ConversationState] = {}
        self._initialized = False
        self._use_redis = settings.redis_enabled and REDIS_AVAILABLE
        self._redis_url: Optional[str] = None
        self._loop_id: Optional[int] = None  # Track which loop owns the Redis client
        
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
        Creates a new client if needed or if event loop has changed.
        """
        if not self._use_redis or not self._redis_url:
            return
        
        # Get current event loop ID
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            # No running loop
            return
        
        # Check if client exists and is bound to current loop
        needs_new_client = (
            self._redis_client is None or
            self._loop_id != current_loop_id
        )
        
        # If client exists but wrong loop, close it first
        if self._redis_client and self._loop_id != current_loop_id:
            try:
                await self._redis_client.aclose()
                logger.debug(f"Closed Redis client from old event loop")
            except Exception as e:
                logger.warning(f"Error closing old Redis client: {e}")
            finally:
                self._redis_client = None
        
        # Create new client if needed
        if needs_new_client:
            try:
                # Create Redis client bound to current event loop
                self._redis_client = redis.from_url(  # type: ignore[union-attr]
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=settings.redis_timeout,
                    socket_connect_timeout=settings.redis_timeout,
                    health_check_interval=30,
                )
                
                # Test connection
                await self._redis_client.ping()  # type: ignore[union-attr]
                
                # Store the loop ID
                self._loop_id = current_loop_id
                
                # Mask password in logs
                safe_url = self._redis_url.replace(settings.redis_password or "", "***") if settings.redis_password else self._redis_url
                logger.info(f"Connected to Redis: {safe_url} (loop_id: {current_loop_id})")
                logger.info(f"Conversation TTL: {settings.conversation_state_ttl}s")
                
            except (RedisConnectionError, RedisError) as e:  # type: ignore[misc]
                logger.error(
                    f"Failed to connect to Redis: {e.__class__.__name__}: {str(e)}. "  # type: ignore[misc]
                    f"Falling back to in-memory storage."
                )
                self._redis_client = None
                self._loop_id = None
                self._use_redis = False
            except Exception as e:  # type: ignore[unreachable]
                logger.error(
                    f"Unexpected error initializing Redis: {e.__class__.__name__}: {str(e)}. "
                    f"Falling back to in-memory storage."
                )
                self._redis_client = None
                self._loop_id = None
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
                self._loop_id = None
        
        self._in_memory_store.clear()
        self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        """
        Check if the state manager has been initialized.
        
        Returns:
            True if initialized, False otherwise.
        """
        return self._initialized
    
    def _generate_conversation_id(self) -> str:
        """Generate a new UUID v4 conversation ID (internal)."""
        return str(uuid.uuid4())

    def generate_conversation_id(self) -> str:
        """Generate a new UUID v4 conversation ID (public API for testing and downstream use)."""
        return self._generate_conversation_id()
    
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
            
            except (RedisError, json.JSONDecodeError) as e:  # type: ignore[misc]
                logger.error(
                    f"Error retrieving conversation {conversation_id} from Redis: {e}. "
                    f"Falling back to in-memory."
                )
                # Fallback to in-memory
                return self._in_memory_store.get(conversation_id)
        
        else:
            # Use in-memory storage
            return self._in_memory_store.get(conversation_id)
    
    async def save_state(self, state: ConversationState) -> None:
        """
        Save conversation state (public API).
        
        Use this method to persist a ConversationState object.
        
        Args:
            state: ConversationState to store
        """
        await self._store_state(state)
    
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
                async for key in self._redis_client.scan_iter(match=pattern):  # type: ignore[misc]
                    keys.append(key)  # type: ignore[arg-type]
                
                if keys:
                    deleted = await self._redis_client.delete(*keys)  # type: ignore[arg-type]
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
