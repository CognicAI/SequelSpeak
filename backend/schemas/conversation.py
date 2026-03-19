"""
Conversation State Schemas

Defines the data structures and enums for conversation state management.
Aligned with SRS v2 Section 6.1 (ConversationState schema).

This module provides:
- ExecutionStage: Enum for conversation flow stages
- ConversationStatus: Enum for conversation lifecycle status
- TurnStatus: Enum for per-turn lifecycle
- QueryType: Enum for query classification (new / follow_up / clarification_response)
- ConversationTurn: Per-turn state model
- ALLOWED_TRANSITIONS: State machine transition rules
- ConversationStateSchema: Complete state structure for persistence
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field, ConfigDict


class ExecutionStage(str, Enum):
    """
    Execution stage in the conversation flow.
    
    Represents the current position in the persona execution pipeline.
    Each stage corresponds to a persona or major processing step.
    
    SRS Reference: Section 6.1, Field: current_stage
    """
    
    # Initial stages
    PLANNING = "planning"  # Router is determining execution plan
    CLARIFICATION = "clarification"  # Clarification persona asking questions
    
    # Core execution stages
    SCHEMA_RETRIEVAL = "schema_retrieval"  # SchemaExpert retrieving schema
    CONTEXT_RETRIEVAL = "context_retrieval"  # ContextRetriever finding examples
    SQL_GENERATION = "sql_generation"  # SQLWriter generating SQL
    VALIDATION = "validation"  # SQLGuardian validating SQL
    EXECUTION = "execution"  # Executor running SQL
    EXPLANATION = "explanation"  # Explainer generating explanation
    ANALYTICS = "analytics"  # Analytics persona determining visualization
    
    # Terminal stages
    COMPLETE = "complete"  # Conversation completed successfully
    ERROR = "error"  # Conversation failed with error
    CANCELLED = "cancelled"  # User cancelled conversation
    TIMEOUT = "timeout"  # Conversation timed out (no response)


class ConversationStatus(str, Enum):
    """
    High-level status of the conversation lifecycle.
    
    Used for client polling and UI state management.
    More coarse-grained than ExecutionStage.
    
    SRS Reference: Section 7.6 (Status Codes)
    """
    
    CLARIFICATION_NEEDED = "clarification_needed"  # Awaiting user response
    PROCESSING = "processing"  # Persona execution in progress
    COMPLETE = "complete"  # Results ready
    ERROR = "error"  # Execution failed
    CANCELLED = "cancelled"  # User cancelled
    TIMEOUT = "timeout"  # Conversation expired


# ---------------------------------------------------------------------------
# Turn-level types
# ---------------------------------------------------------------------------

class TurnStatus(str, Enum):
    """
    Lifecycle status of a single conversation turn.
    
    A conversation is composed of multiple turns, each with its own lifecycle.
    """
    
    IN_PROGRESS = "in_progress"              # Turn is actively being processed
    CLARIFICATION_PAUSED = "clarification_paused"  # Waiting for user clarification
    COMPLETE = "complete"                     # Turn completed successfully
    ERROR = "error"                           # Turn failed


class QueryType(str, Enum):
    """
    Classification of a query relative to the conversation history.
    
    Used by the Router to decide how much prior context to inject.
    """
    
    NEW = "new"                              # Unrelated to previous turns
    FOLLOW_UP = "follow_up"                  # Builds on / refines previous turn
    CLARIFICATION_RESPONSE = "clarification_response"  # Answer to a clarification question


class ConversationTurn(BaseModel):
    """
    Represents a single turn in a multi-turn conversation.
    
    Each turn tracks the user's query (original and refined), its lifecycle,
    and the results produced by the persona pipeline.
    
    Query Field Ownership:
    - original_query: What the user typed, verbatim. Immutable.
    - refined_query:  After clarification merging. Set once by refinement logic.
    """
    
    turn_id: str = Field(..., description="UUID v4 identifier for this turn")
    turn_number: int = Field(..., description="1-indexed sequential turn number")
    original_query: str = Field(..., description="User's query as submitted (immutable)")
    refined_query: Optional[str] = Field(
        default=None,
        description="Query after clarification merging (None if no clarification)"
    )
    query_type: QueryType = Field(
        default=QueryType.NEW,
        description="Classification: new, follow_up, or clarification_response"
    )
    status: TurnStatus = Field(
        default=TurnStatus.IN_PROGRESS,
        description="Current lifecycle status of this turn"
    )
    paused_at_stage: Optional[str] = Field(
        default=None,
        description="ExecutionStage value where clarification paused this turn"
    )
    generated_sql: Optional[str] = Field(default=None, description="SQL produced this turn")
    execution_result: Optional[Dict[str, Any]] = Field(
        default=None, description="Query results from this turn"
    )
    explanation: Optional[str] = Field(default=None, description="Explanation from this turn")
    started_at: str = Field(..., description="ISO 8601 timestamp when turn started")
    completed_at: Optional[str] = Field(
        default=None, description="ISO 8601 timestamp when turn finished"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "turn_id": "f1e2d3c4-b5a6-4978-8a9b-0c1d2e3f4a5b",
                "turn_number": 1,
                "original_query": "Show sales from last month",
                "refined_query": None,
                "query_type": "new",
                "status": "complete",
                "paused_at_stage": None,
                "generated_sql": "SELECT * FROM sales WHERE ...",
                "execution_result": {"rows": [], "row_count": 0},
                "explanation": "Your query returned 0 rows.",
                "started_at": "2026-03-05T10:30:00Z",
                "completed_at": "2026-03-05T10:30:12Z",
            }
        }
    )


# ---------------------------------------------------------------------------
# State machine: allowed status transitions
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: Dict[ConversationStatus, Set[ConversationStatus]] = {
    ConversationStatus.PROCESSING: {
        ConversationStatus.COMPLETE,
        ConversationStatus.ERROR,
        ConversationStatus.CLARIFICATION_NEEDED,
        ConversationStatus.CANCELLED,
        ConversationStatus.TIMEOUT,
        ConversationStatus.PROCESSING,  # same-turn retry (SQL validation loop)
    },
    ConversationStatus.CLARIFICATION_NEEDED: {
        ConversationStatus.PROCESSING,
        ConversationStatus.CANCELLED,
        ConversationStatus.TIMEOUT,
    },
    ConversationStatus.COMPLETE: {
        ConversationStatus.PROCESSING,  # new turn
    },
    ConversationStatus.ERROR: {
        ConversationStatus.PROCESSING,  # retry / new turn
    },
    ConversationStatus.CANCELLED: set(),  # terminal
    ConversationStatus.TIMEOUT: set(),    # terminal
}

# Maximum number of completed turns retained in state. Older turns evicted FIFO.
MAX_TURNS = 20


class InvalidStateTransition(Exception):
    """Raised when a status transition violates the state machine rules."""
    
    def __init__(self, current: ConversationStatus, target: ConversationStatus):
        self.current = current
        self.target = target
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        allowed_str = ', '.join([s.value for s in allowed]) if allowed else 'none (terminal)'
        super().__init__(
            f"Invalid state transition: {current.value} → {target.value}. "
            f"Allowed targets from {current.value}: {allowed_str}"
        )


class ClarificationQuestion(BaseModel):
    """
    A single clarification question asked to the user.
    
    Part of the clarification_history array.
    """
    
    question: str = Field(..., description="Question text")
    answer: Optional[str] = Field(default=None, description="User's answer (None if not yet answered)")
    timestamp: str = Field(..., description="ISO 8601 timestamp when question was asked")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What time period are you interested in?",
                "answer": "Last month",
                "timestamp": "2026-03-05T10:30:00Z"
            }
        }
    )


class PersonaTraceEntry(BaseModel):
    """
    A single entry in the persona execution trace.
    
    Logs the input/output of each persona for debugging and observability.
    SRS Reference: Section 6.1, Field: persona_trace
    """
    
    persona_name: str = Field(..., description="Name of the persona (e.g., 'Router', 'SchemaExpert')")
    stage: ExecutionStage = Field(..., description="Execution stage when persona ran")
    input_data: Dict[str, Any] = Field(default_factory=lambda: {}, description="Persona input contract")
    output_data: Dict[str, Any] = Field(default_factory=lambda: {}, description="Persona output contract")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Execution duration in milliseconds")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "persona_name": "Router",
                "stage": "planning",
                "input_data": {"nl_query": "Show sales"},
                "output_data": {"next_persona": "Clarification", "requires_clarification": True},
                "timestamp": "2026-03-05T10:30:00Z",
                "duration_ms": 45.2
            }
        }
    )


class ErrorRecord(BaseModel):
    """
    Error record for failed stages.
    
    SRS Reference: Section 6.1, Field: errors
    """
    
    stage: ExecutionStage = Field(..., description="Stage where error occurred")
    error_type: str = Field(..., description="Error type/class name")
    error_message: str = Field(..., description="Human-readable error message")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stage": "validation",
                "error_type": "ValidationError",
                "error_message": "SQL contains non-existent column 'sales_amount'",
                "timestamp": "2026-03-05T10:30:00Z",
                "retry_count": 1
            }
        }
    )


class ConversationStateSchema(BaseModel):
    """
    Complete conversation state schema for persistence.
    
    This schema defines all 18 fields required by SRS v2 Section 6.1.
    Used for serialization/deserialization with Redis/database.
    Acts as the authoritative schema for the persisted ConversationState.
    """
    
    # ===== Core Identity Fields =====
    conversation_id: str = Field(..., description="UUID v4 conversation identifier")
    session_start_time: str = Field(..., description="ISO 8601 timestamp when conversation began")
    
    # ===== Query Fields =====
    original_nl_query: str = Field(..., description="User's original natural language question")
    current_nl_query: Optional[str] = Field(
        default=None,
        description="Refined query after clarification (None if no clarification)"
    )
    
    # ===== Parameter Resolution =====
    resolved_parameters: Dict[str, Any] = Field(
        default_factory=lambda: {},
        description="Resolved parameters: time_range, granularity, metric, filters"
    )
    
    # ===== Clarification Fields =====
    pending_clarification_questions: List[str] = Field(
        default_factory=lambda: [],
        description="Questions awaiting user response"
    )
    clarification_history: List[ClarificationQuestion] = Field(
        default_factory=lambda: [],
        description="Q&A pairs from clarification rounds"
    )
    awaiting_user_response: bool = Field(
        default=False,
        description="True if execution paused for clarification"
    )
    
    # ===== Execution Flow Fields =====
    current_stage: ExecutionStage = Field(
        default=ExecutionStage.PLANNING,
        description="Current position in execution pipeline"
    )
    status: ConversationStatus = Field(
        default=ConversationStatus.PROCESSING,
        description="High-level conversation status"
    )
    execution_plan: List[str] = Field(
        default_factory=lambda: [],
        description="Ordered persona names to execute (e.g., ['SchemaExpert', 'SQLWriter', ...])"
    )
    completed_stages: List[str] = Field(
        default_factory=lambda: [],
        description="Personas that finished successfully"
    )
    
    # ===== Result Fields =====
    generated_sql: Optional[str] = Field(
        default=None,
        description="SQLWriter output (final validated SQL)"
    )
    execution_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Query results from Executor (rows, columns, metadata)"
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Explainer output (plain English explanation)"
    )
    visualization_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Analytics persona output (chart type, time bucket, etc.)"
    )
    
    # ===== Observability Fields =====
    persona_trace: List[PersonaTraceEntry] = Field(
        default_factory=lambda: [],
        description="Log of persona inputs/outputs for debugging"
    )
    errors: List[ErrorRecord] = Field(
        default_factory=lambda: [],
        description="Error records from failed stages"
    )
    
    # ===== Metadata Fields =====
    updated_at: str = Field(..., description="ISO 8601 timestamp of last update")
    
    # ===== Turn Tracking Fields (multi-turn support) =====
    current_turn_id: Optional[str] = Field(
        default=None,
        description="UUID v4 of the active turn (None before first turn starts)"
    )
    turn_number: int = Field(
        default=0,
        description="Current turn number (0 = no turns started yet)"
    )
    turns: List[Dict[str, Any]] = Field(
        default_factory=lambda: [],
        description="Completed turn snapshots (capped at MAX_TURNS, FIFO eviction)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "session_start_time": "2026-03-05T10:30:00Z",
                "original_nl_query": "Show sales from last month",
                "current_nl_query": "Show sales from February 2026",
                "resolved_parameters": {
                    "time_range": {"start": "2026-02-01", "end": "2026-02-29"},
                    "metric": "sales"
                },
                "pending_clarification_questions": [],
                "clarification_history": [],
                "awaiting_user_response": False,
                "current_stage": "sql_generation",
                "status": "processing",
                "execution_plan": ["SchemaExpert", "ContextRetriever", "SQLWriter", "SQLGuardian", "Executor", "Explainer"],
                "completed_stages": ["SchemaExpert", "ContextRetriever"],
                "generated_sql": None,
                "execution_result": None,
                "explanation": None,
                "visualization_config": None,
                "persona_trace": [],
                "errors": [],
                "updated_at": "2026-03-05T10:31:00Z"
            }
        }
    )


class SessionMetadata(BaseModel):
    """
    Additional metadata stored in ConversationState.metadata.
    
    This is NOT part of the SRS 18-field schema but provides auxiliary context.
    Used for user tracking, debugging, and analytics.
    """
    
    user_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User context from RouterRequest (user_id, session_id, ip_address)"
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Request correlation ID for tracing"
    )
    database_id: Optional[str] = Field(
        default=None,
        description="Target database identifier (if multi-database support is added)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_context": {
                    "user_id": None,
                    "session_id": "session-abc-123",
                    "ip_address": "192.168.1.1"
                },
                "correlation_id": "req-12345678",
                "database_id": "prod-db-001"
            }
        }
    )
