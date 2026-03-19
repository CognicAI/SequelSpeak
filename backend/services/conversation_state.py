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
from typing import Optional, Dict, Any, List, TYPE_CHECKING, AsyncGenerator, cast

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
    TurnStatus,
    QueryType,
    ConversationTurn,
    ALLOWED_TRANSITIONS,
    MAX_TURNS,
    InvalidStateTransition,
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
        # Turn tracking fields
        current_turn_id: Optional[str] = None,
        turn_number: int = 0,
        turns: Optional[List[Dict[str, Any]]] = None,
        clarification_rounds: int = 0,
        # Legacy fields for backward compatibility
        created_at: Optional[str] = None,
    ):
        """
        Initialize conversation state.
        
        Args:
            conversation_id: UUID v4 conversation ID
            session_start_time: ISO 8601 creation timestamp (auto-generated if None)
            original_nl_query: User's original query (immutable conversation identity)
            current_nl_query: Active query for pipeline execution (updated per turn)
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
            current_turn_id: UUID v4 of the active turn
            turn_number: Current turn number (0 = no turns started)
            turns: Completed turn snapshots (capped at MAX_TURNS)
            created_at: Legacy field, maps to session_start_time
        """
        self.conversation_id = conversation_id
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Core identity fields
        self.session_start_time = session_start_time or created_at or now
        
        # Query fields
        # original_nl_query: immutable — first-ever query for conversation identity
        # current_nl_query: mutable — the query the pipeline should execute RIGHT NOW
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
        
        # Turn tracking
        self.current_turn_id = current_turn_id
        self.turn_number = turn_number
        self.turns: List[Dict[str, Any]] = turns or []
        self.clarification_rounds = clarification_rounds
    
    # Legacy property for backward compatibility
    @property
    def created_at(self) -> str:
        """Backward compatibility: created_at maps to session_start_time."""
        return self.session_start_time
    
    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------
    
    def start_new_turn(
        self,
        query: str,
        query_type: QueryType = QueryType.NEW,
    ) -> ConversationTurn:
        """
        Start a new turn in this conversation.
        
        1. Snapshots the current turn (if any) into self.turns[]
        2. Evicts oldest turns beyond MAX_TURNS
        3. Creates a fresh ConversationTurn
        4. Resets per-turn execution state
        5. Updates current_nl_query (original_nl_query stays immutable)
        
        Args:
            query: The user's new query text
            query_type: Classification of the query
        
        Returns:
            The newly created ConversationTurn
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Snapshot current turn if it exists and is finished
        if self.current_turn_id and self.turn_number > 0:
            snapshot: Dict[str, Any] = {
                'turn_id': self.current_turn_id,
                'turn_number': self.turn_number,
                'original_query': self.current_nl_query or self.original_nl_query or '',
                'refined_query': None,
                'query_type': query_type.value,  # previous turn's type
                'status': TurnStatus.COMPLETE.value,
                'paused_at_stage': None,
                'generated_sql': self.generated_sql,
                'execution_result': self.execution_result,
                'explanation': self.explanation,
                'started_at': self.metadata.get('_turn_started_at', now),
                'completed_at': now,
            }
            self.turns.append(snapshot)
            # FIFO eviction
            if len(self.turns) > MAX_TURNS:
                self.turns = self.turns[-MAX_TURNS:]
        
        # Increment turn
        self.turn_number += 1
        new_turn_id = str(uuid.uuid4())
        self.current_turn_id = new_turn_id
        
        # Update query fields
        # original_nl_query stays immutable — only set on first turn
        if self.original_nl_query is None:
            self.original_nl_query = query
        self.current_nl_query = query
        
        # Reset per-turn execution state
        self.generated_sql = None
        self.execution_result = None
        self.explanation = None
        self.errors = []
        self.completed_stages = []
        self.persona_trace = []
        self.awaiting_user_response = False
        self.pending_clarification_questions = []
        self.clarification_rounds = 0
        
        # Store turn start time in metadata for snapshot
        self.metadata['_turn_started_at'] = now
        
        # Create the turn model
        turn = ConversationTurn(
            turn_id=new_turn_id,
            turn_number=self.turn_number,
            original_query=query,
            query_type=query_type,
            status=TurnStatus.IN_PROGRESS,
            started_at=now,
        )
        
        self.updated_at = now
        return turn
    
    def transition_status(self, new_status: ConversationStatus) -> None:
        """
        Transition to a new conversation status with validation.
        
        Raises InvalidStateTransition if the transition is not allowed
        by the state machine rules.
        
        Args:
            new_status: Target ConversationStatus
        
        Raises:
            InvalidStateTransition: If transition is illegal
        """
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidStateTransition(self.status, new_status)
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def refine_query_after_clarification(
        self,
        q_and_a_pairs: List[Dict[str, str]],
    ) -> str:
        """
        Build a refined query from the original query + clarification Q&A.
        
        Uses template-based refinement:
          "{original_query}, where {q1_key} is {a1} and {q2_key} is {a2}"
        
        Example:
          original = "show price"
          Q: "which product?"  A: "BMW"
          → "show price, where product is BMW"
        
        TODO: Replace with LLM-based refinement when real LLM integration lands.
        
        Args:
            q_and_a_pairs: List of dicts with 'question' and 'answer' keys
        
        Returns:
            The refined query string
        """
        base_query = self.current_nl_query or self.original_nl_query or ''
        
        if not q_and_a_pairs:
            return base_query
        
        # Extract context from Q&A pairs
        clauses: List[str] = []
        for pair in q_and_a_pairs:
            question = pair.get('question', '').strip()
            answer = pair.get('answer', '').strip()
            if not answer:
                continue
            
            # Extract the key concept from the question
            # Remove common question prefixes/suffixes
            key = question.lower()
            for prefix in ('what ', 'which ', 'what is the ', 'which is the ',
                          'please specify the ', 'specify the '):
                if key.startswith(prefix):
                    key = key[len(prefix):]
                    break
            # Remove trailing punctuation
            key = key.rstrip('?').strip()
            
            if key:
                clauses.append(f"{key} is {answer}")
            else:
                clauses.append(answer)
        
        if clauses:
            refined = f"{base_query}, where {' and '.join(clauses)}"
        else:
            refined = base_query
        
        # Update state
        self.current_nl_query = refined
        self.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        return refined
    
    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-merge two dictionaries. Nested dicts are merged recursively;
        all other types are overwritten by the override value.
        
        Args:
            base: Base dictionary
            override: Override dictionary (takes precedence)
        
        Returns:
            Merged dictionary (new object; inputs are not mutated)
        """
        result = dict(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                nested_base = cast(Dict[str, Any], result[key])
                nested_override = cast(Dict[str, Any], value)
                result[key] = ConversationState._deep_merge(nested_base, nested_override)
            else:
                result[key] = value
        return result
    
    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    
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
            
            # Turn tracking
            'current_turn_id': self.current_turn_id,
            'turn_number': self.turn_number,
            'turns': self.turns,
            'clarification_rounds': self.clarification_rounds,
            
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
            current_turn_id=data.get('current_turn_id'),
            turn_number=data.get('turn_number', 0),
            turns=data.get('turns', []),
            clarification_rounds=data.get('clarification_rounds', 0),
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
        self._subscribers: Dict[str, set[asyncio.Queue[str]]] = {} # Local pub/sub fallback
        
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
        
        # Publish event for SSE listeners
        data = json.dumps(state.to_dict())
        
        # 1. Publish to Redis if available
        if self._use_redis and self._redis_client:
            try:
                channel = f"channel:convo:{state.conversation_id}"
                await self._redis_client.publish(channel, data)  # type: ignore
            except Exception as e:
                logger.error(f"Failed to publish state to Redis pubsub: {e}")
                
        # 2. Always publish to local memory queues just in case
        if state.conversation_id in self._subscribers:
            for q in self._subscribers[state.conversation_id]:
                q.put_nowait(data)

    async def listen(self, conversation_id: str) -> AsyncGenerator[str, None]:
        """
        Listen for updates on a given conversation id via Pub/Sub.
        Yields JSON strings of the conversation state.
        """
        if self._use_redis:
            await self._ensure_redis_client()
            
        if self._use_redis and self._redis_client:
            # Using Redis Pub/Sub
            pubsub = self._redis_client.pubsub()  # type: ignore
            channel = f"channel:convo:{conversation_id}"
            await pubsub.subscribe(channel)  # type: ignore
            try:
                async for message in pubsub.listen():  # type: ignore
                    if message and message['type'] == 'message':  # type: ignore
                        # Redis gives us bytes or str depending on config
                        data = message['data']  # type: ignore
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        elif not isinstance(data, str):
                            data = str(data)  # type: ignore
                        yield data
            finally:
                await pubsub.unsubscribe(channel)  # type: ignore
                await pubsub.close()
        else:
            # Using in-memory queue fallback
            q: asyncio.Queue[str] = asyncio.Queue()
            if conversation_id not in self._subscribers:
                self._subscribers[conversation_id] = set()
            self._subscribers[conversation_id].add(q)
            try:
                while True:
                    data = await q.get()
                    yield data
                    q.task_done()
            finally:
                if conversation_id in self._subscribers:
                    self._subscribers[conversation_id].discard(q)
                    if not self._subscribers[conversation_id]:
                        del self._subscribers[conversation_id]

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
