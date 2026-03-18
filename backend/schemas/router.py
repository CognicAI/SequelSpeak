"""
Router Request and Response Schemas

Defines the strict contract for Router entry point inputs/outputs.
Aligned with SRS v2 Router specifications.
"""

from typing import Optional, Literal, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum
import re
from utils.security import SENSITIVE_USER_CONTEXT_FIELDS


class RouterErrorCode(str, Enum):
    """Router-specific error codes for request validation."""
    
    INVALID_QUERY = "INVALID_QUERY"
    QUERY_TOO_LONG = "QUERY_TOO_LONG"
    QUERY_EMPTY = "QUERY_EMPTY"
    INVALID_CONVERSATION_ID = "INVALID_CONVERSATION_ID"
    INVALID_REQUEST = "INVALID_REQUEST"


# Configuration constants
MAX_QUERY_LENGTH = 10000  # Maximum query length in characters
MIN_QUERY_LENGTH = 1      # Minimum query length (after stripping whitespace)

# UUID v4 regex pattern for validation
UUID_V4_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE
)


class UserContext(BaseModel):
    """
    User context metadata for request tracing and session management.
    
    Currently a placeholder structure for future authentication/authorization.
    All fields are optional as the system does not yet have an auth layer.
    """
    
    user_id: Optional[str] = Field(
        default=None,
        description="User identifier (placeholder for future auth system)"
    )
    
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for tracking user sessions"
    )
    
    ip_address: Optional[str] = Field(
        default=None,
        description="Client IP address for security/audit purposes (never logged)"
    )

    def safe_dict(self) -> dict[str, Any]:
        """
        Return model data with sensitive fields excluded, safe for logging.

        Always use this method when building log messages that include
        user/session metadata. Use model_dump() only for persistence.

        Excluded fields: ip_address
        """
        return {k: v for k, v in self.model_dump().items() if k not in SENSITIVE_USER_CONTEXT_FIELDS}

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": None,
                "session_id": None,
                "ip_address": None
            }
        }
    )


class RouterRequest(BaseModel):
    """
    Router entry point request schema.
    
    Represents the input contract for all natural language queries entering
    the SequelSpeak system. This is the mandatory entry point for the Router
    persona before any LLM processing or routing decisions occur.
    
    Schema Version: 1.0.0
    """
    
    query: str = Field(
        ...,
        description=(
            "Natural language query from the user. "
            "Examples: 'Show sales from last month', 'How many active users?'"
        ),
        json_schema_extra={
            "example": "Show me the total revenue for Q4 2025"
        }
    )
    
    conversation_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional conversation ID for multi-turn conversations. "
            "Must be a valid UUID v4 format. If not provided, a new UUID will be generated."
        ),
        json_schema_extra={
            "example": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        }
    )

    database_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID of the saved connection profile to query against. "
            "Stored in conversation metadata for use by the orchestrator."
        ),
        json_schema_extra={
            "example": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
        }
    )
    
    user_context: UserContext | None = Field(
        default=None,
        description="Optional user and session metadata for tracking"
    )
    
    @field_validator('query', mode='before')
    @classmethod
    def validate_query(cls, v: object) -> str:
        """
        Validate query string content and format.
        
        Validation Rules:
        - Cannot be empty after stripping whitespace
        - Cannot contain only whitespace
        - Cannot contain null bytes
        - Must be within length limits
        
        Args:
            v: Query string to validate
            
        Returns:
            Validated query string (whitespace-stripped)
            
        Raises:
            ValueError: If query fails validation
        """
        # Handle None or non-string types
        if v is None or not isinstance(v, str):
            raise ValueError("Query must be a string and cannot be None")
        
        # Strip leading/trailing whitespace
        v_stripped = v.strip()
        
        # Check for empty query after stripping
        if not v_stripped:
            raise ValueError(
                "Query cannot be empty or contain only whitespace"
            )
        
        # Check for null bytes (security validation)
        if '\x00' in v:
            raise ValueError(
                "Query contains invalid null bytes"
            )
        
        # Check for URL-encoded null bytes
        if '%00' in v.lower():
            raise ValueError(
                "Query contains invalid null bytes"
            )
        
        # Length validation on stripped value
        if len(v_stripped) < MIN_QUERY_LENGTH:
            raise ValueError(
                f"Query must be at least {MIN_QUERY_LENGTH} character(s) long"
            )
        
        if len(v_stripped) > MAX_QUERY_LENGTH:
            raise ValueError(
                f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters"
            )
        
        return v_stripped
    
    @field_validator('conversation_id')
    @classmethod
    def validate_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate conversation ID format (UUID v4).
        
        Validation Rules:
        - If provided, must be a valid UUID v4 format
        - If None or empty string, returns None (will be generated later)
        - Case-insensitive validation
        - Normalized to lowercase
        
        Args:
            v: Conversation ID to validate
            
        Returns:
            Validated conversation ID (lowercase) or None
            
        Raises:
            ValueError: If conversation_id is provided but invalid
        """
        # Allow None or empty string (will be generated by service layer)
        if v is None or v == "":
            return None
        
        # Strip whitespace
        v_stripped = v.strip()
        
        if not v_stripped:
            return None
        
        # Validate UUID v4 format
        if not UUID_V4_PATTERN.match(v_stripped):
            raise ValueError(
                "Conversation ID must be a valid UUID v4 format "
                "(e.g., 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d')"
            )
        
        # Normalize to lowercase for consistency
        return v_stripped.lower()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Show me the total revenue for Q4 2025",
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "user_context": {
                    "user_id": None,
                    "session_id": None,
                    "ip_address": None
                }
            }
        }
    )


class RouterInitResponse(BaseModel):
    """
    Successful response from Router initialization.
    
    Returned when a query is successfully validated and initialized
    with conversation and request metadata.
    """
    
    status: Literal["success"] = Field(
        default="success",
        description="Request initialization status"
    )
    
    conversation_id: str = Field(
        ...,
        description="Conversation ID for this request (generated or provided, UUID v4 format)"
    )
    
    @field_validator('conversation_id')
    @classmethod
    def validate_conversation_id_format(cls, v: str) -> str:
        """Validate that conversation_id is a valid UUID v4 format."""
        if not UUID_V4_PATTERN.match(v):
            raise ValueError(
                f"Conversation ID must be a valid UUID v4 format, got: {v}"
            )
        return v.lower()
    
    query: str = Field(
        ...,
        description="The validated and normalized query string"
    )
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of request initialization"
    )
    
    correlation_id: Optional[str] = Field(
        default=None,
        description="Correlation ID for request tracing (from middleware)"
    )
    
    message: str = Field(
        default="Query initialized successfully",
        description="Human-readable success message"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "query": "Show me the total revenue for Q4 2025",
                "timestamp": "2026-02-08T10:30:00Z",
                "correlation_id": "req-12345678-90ab-cdef-1234-567890abcdef",
                "message": "Query initialized successfully"
            }
        }
    )


class RouterErrorResponse(BaseModel):
    """
    Error response from Router initialization.
    
    Follows the existing error response pattern from connection.py
    """
    
    detail: str = Field(
        ...,
        description="Human-readable error message"
    )
    
    error_code: RouterErrorCode = Field(
        ...,
        description="Machine-readable error code for programmatic handling"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Query cannot be empty or contain only whitespace",
                "error_code": "QUERY_EMPTY"
            }
        }
    )


# Schema version for API versioning
ROUTER_SCHEMA_VERSION = "1.0.0"


class QueryStatusResponse(BaseModel):
    """
    Response from GET /api/v1/query/status/{conversation_id}.

    Returns the current snapshot of a running conversation so the
    frontend can update its chat UI without server-sent events.
    """

    conversation_id: str = Field(..., description="UUID v4 conversation identifier")
    status: str = Field(..., description="ConversationStatus value (processing, clarification_needed, complete, error, timeout, cancelled)")
    current_stage: str = Field(..., description="Current ExecutionStage value")
    awaiting_user_response: bool = Field(default=False, description="True if execution is paused for clarification")
    pending_clarification_questions: list[str] = Field(
        default_factory=list,
        description="Questions awaiting user answer"
    )
    generated_sql: Optional[str] = Field(default=None, description="SQL produced by SQLWriter, if available")
    execution_result: Optional[Any] = Field(default=None, description="Query result rows/metadata from Executor")
    explanation: Optional[str] = Field(default=None, description="Plain-English explanation from Explainer")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "status": "clarification_needed",
                "current_stage": "clarification",
                "awaiting_user_response": True,
                "pending_clarification_questions": ["What time period are you interested in?"],
                "generated_sql": None,
                "execution_result": None,
                "explanation": None,
            }
        }
    )


class QueryRespondRequest(BaseModel):
    """
    Body for POST /api/v1/query/respond.

    Submits user answers to pending clarification questions.
    The same conversation_id is preserved so the backend can resume execution
    from where it paused.
    """

    conversation_id: str = Field(..., description="UUID v4 of the conversation to resume")
    answers: list[str] = Field(
        default_factory=list,
        description="Answer strings, one per pending clarification question"
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional free-form follow-up message (used instead of answers for open-ended turns)"
    )
    database_id: Optional[str] = Field(
        default=None,
        description="Override database profile if the user switched connection mid-conversation"
    )

    @field_validator('conversation_id')
    @classmethod
    def validate_respond_conversation_id(cls, v: str) -> str:
        """Validate UUID v4 format on respond request."""
        if not UUID_V4_PATTERN.match(v.strip()):
            raise ValueError(
                "conversation_id must be a valid UUID v4 format"
            )
        return v.strip().lower()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "answers": ["Last 30 days"],
                "message": None,
                "database_id": None,
            }
        }
    )


class QueryRespondResponse(BaseModel):
    """Response from POST /api/v1/query/respond."""

    conversation_id: str = Field(..., description="Same UUID v4 as the request")
    status: str = Field(..., description="Updated ConversationStatus after applying answers")
    current_stage: str = Field(..., description="Updated ExecutionStage")
    message: str = Field(default="Clarification answers recorded", description="Human-readable confirmation")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "status": "processing",
                "current_stage": "planning",
                "message": "Clarification answers recorded",
            }
        }
    )

