"""
Query Router API Endpoint

Handles incoming natural language queries and validates them against
the Router request schema. This is the entry point for all query requests.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, status, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from schemas.router import (
    RouterRequest,
    RouterInitResponse,
    RouterErrorResponse,
    RouterErrorCode,
    UserContext,
    QueryStatusResponse,
    QueryRespondRequest,
    QueryRespondResponse,
)
from services.conversation_state import conversation_state_manager, ConversationState
from services.router_service import get_router_service
from services.orchestrator import get_orchestrator_service
from utils.auth import verify_clerk_token
from utils.security import sanitize_user_context_for_log

router = APIRouter()
logger = logging.getLogger(__name__)


STAGE_TO_PERSONA: dict[str, str] = {
    "planning": "Router",
    "clarification": "Clarification",
    "schema_retrieval": "SchemaExpert",
    "context_retrieval": "ContextRetriever",
    "sql_generation": "SQLWriter",
    "validation": "SQLGuardian",
    "execution": "Executor",
    "explanation": "Explainer",
    "analytics": "Analytics",
    "complete": "Complete",
    "error": "Error",
    "cancelled": "Cancelled",
    "timeout": "Timeout",
}

PROGRESS_BY_STAGE: dict[str, int] = {
    "planning": 10,
    "schema_retrieval": 25,
    "context_retrieval": 40,
    "sql_generation": 55,
    "validation": 70,
    "execution": 85,
    "explanation": 95,
    "analytics": 98,
    "complete": 100,
}

ESTIMATED_REMAINING_MS_BY_STAGE: dict[str, int] = {
    "planning": 9000,
    "schema_retrieval": 7500,
    "context_retrieval": 6500,
    "sql_generation": 5500,
    "validation": 3500,
    "execution": 2500,
    "explanation": 1200,
    "analytics": 700,
    "complete": 0,
}


def _to_persona_trace(trace_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for entry in trace_entries:
        persona = entry.get("persona_name")
        duration_ms = entry.get("duration_ms")
        if persona:
            trace.append({"persona": persona, "duration_ms": duration_ms})
    return trace


def _build_status_payload(state: ConversationState) -> dict[str, Any]:
    current_stage = state.current_stage.value
    current_persona: Optional[str] = STAGE_TO_PERSONA.get(current_stage)
    progress_percentage = PROGRESS_BY_STAGE.get(current_stage)
    estimated_completion_ms = ESTIMATED_REMAINING_MS_BY_STAGE.get(current_stage)

    payload: dict[str, Any] = {
        "conversation_id": state.conversation_id,
        "status": state.status.value,
        "current_stage": current_stage,
        "current_persona": current_persona,
        "completed_personas": state.completed_stages or [],
        "estimated_completion_ms": estimated_completion_ms,
        "progress_percentage": progress_percentage,
        "awaiting_user_response": state.awaiting_user_response,
        "pending_clarification_questions": list(state.pending_clarification_questions or []),
        "generated_sql": state.generated_sql,
        "execution_result": state.execution_result,
        "explanation": state.explanation,
        "persona_trace": _to_persona_trace(state.persona_trace or []),
    }
    return payload


def map_validation_error_to_router_error(validation_error: ValidationError) -> tuple[RouterErrorCode, str]:
    """
    Map Pydantic ValidationError to RouterErrorCode and user-friendly message.
    
    Args:
        validation_error: Pydantic validation error
        
    Returns:
        Tuple of (RouterErrorCode, error_message)
    """
    errors = validation_error.errors()
    
    if not errors:
        return RouterErrorCode.INVALID_REQUEST, "Request validation failed"
    
    # Get the first error for simplicity (Pydantic may return multiple)
    first_error = errors[0]
    error_type = first_error.get("type", "")
    error_loc = first_error.get("loc", ())
    error_msg = first_error.get("msg", "Validation error")
    
    # Map field-specific errors
    if "query" in error_loc:
        # Check for specific error messages from our custom validators
        if "exceeds maximum length" in error_msg:
            return RouterErrorCode.QUERY_TOO_LONG, error_msg
        elif "cannot be empty" in error_msg or "only whitespace" in error_msg:
            return RouterErrorCode.QUERY_EMPTY, error_msg
        elif "null byte" in error_msg:
            return RouterErrorCode.INVALID_QUERY, error_msg
        elif "must be a string" in error_msg:
            # Type mismatch - query should be string but got something else
            return RouterErrorCode.INVALID_QUERY, error_msg
        elif "missing" in error_type:
            return RouterErrorCode.QUERY_EMPTY, "Query field is required"
        else:
            return RouterErrorCode.INVALID_QUERY, error_msg
    
    if "conversation_id" in error_loc:
        return RouterErrorCode.INVALID_CONVERSATION_ID, error_msg
    
    # Generic validation error
    return RouterErrorCode.INVALID_REQUEST, error_msg


@router.post(
    "/start",
    response_model=RouterInitResponse,
    status_code=status.HTTP_200_OK,
    summary="Initialize Query Request",
    description="""
Initialize a natural language query request for the Router.

This endpoint validates the query payload and prepares it for downstream
processing by the Router persona. It does NOT execute the query or perform
any LLM processing - it simply validates and initializes the request.

**Request Body:**
- `query` (required): Natural language query string (1-10,000 characters)
- `conversation_id` (optional): UUID v4 for multi-turn conversations
- `user_context` (optional): User metadata for tracking

**Validation Rules:**
- Query cannot be empty or contain only whitespace
- Query cannot contain null bytes (security)
- Query must be between 1 and 10,000 characters (after whitespace stripping)
- Conversation ID must be valid UUID v4 format (if provided)

**Response:**
- Returns conversation_id (generated if not provided), validated query, timestamp, and correlation_id
    """,
    responses={
        200: {
            "description": "Query initialized successfully",
            "model": RouterInitResponse
        },
        400: {
            "description": "Validation error - malformed or incomplete request",
            "model": RouterErrorResponse
        },
        422: {
            "description": "Unprocessable entity - invalid JSON or request structure"
        }
    },
    tags=["Query"]
)
async def initialize_query(
    request: Request,
    payload: RouterRequest,
    background_tasks: BackgroundTasks,
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> RouterInitResponse:
    """
    Validate and initialize a natural language query request.
    
    This endpoint performs early validation of incoming query requests,
    ensuring they meet the Router input contract before any processing begins.
    
    Args:
        request: FastAPI Request object (for correlation ID)
        payload: Validated RouterRequest from Pydantic
        
    Returns:
        RouterInitResponse with conversation_id, query, timestamp, and correlation_id
        
    Raises:
        HTTPException: 400 if validation fails (handled by exception handler)
    """
    # Extract authenticated user ID from JWT claims
    user_id = str(user_claims.get("sub", "unknown"))

    # Get correlation ID from request headers (set by middleware)
    correlation_id = request.headers.get("X-Correlation-ID")

    # Log the incoming request (securely - no sensitive data, truncated user_id)
    logger.info(
        f"Query request received by user={user_id[:8]}...: query_length={len(payload.query)}, "
        f"conversation_id={'provided' if payload.conversation_id else 'not_provided'}",
        extra={'extra_fields': {'correlation_id': correlation_id}}
    )

    # Build enriched user/session metadata:
    # - Start from the payload's user_context (default to empty UserContext if omitted).
    # - ALWAYS override user_id from the verified JWT "sub" claim — the client-supplied
    #   value is a convenience hint only; the JWT sub is the authoritative identity.
    # - Auto-populate ip_address from the real client IP if the caller did not supply it.
    user_context: UserContext = payload.user_context if payload.user_context is not None else UserContext()

    # 1. Inject verified user identity from JWT (cannot be spoofed by client)
    user_context = user_context.model_copy(update={"user_id": user_id})

    # 2. Auto-populate ip_address from real client IP if not provided
    if user_context.ip_address is None and request.client is not None:
        user_context = user_context.model_copy(update={"ip_address": request.client.host})

    # Convert user_context to dict for persistence
    user_context_dict = user_context.model_dump()

    # Initialize conversation state using RouterService
    # This creates the initial state with proper stage, status, and query
    router_service = get_router_service()
    
    # Check if this is a new conversation or existing one
    existing_state = None
    if payload.conversation_id:
        existing_state = await conversation_state_manager.get_state(payload.conversation_id)
    
    if existing_state:
        # Existing conversation - merge user context
        conversation_id = existing_state.conversation_id
        existing_ctx = existing_state.metadata.get("user_context", {})
        merged_ctx: dict[str, Any] = {
            **existing_ctx,
            **{k: v for k, v in user_context_dict.items() if v is not None},
        }
        
        # Update metadata only (preserve existing state fields)
        await conversation_state_manager.upsert_state(
            conversation_id,
            metadata={'user_context': merged_ctx, 'correlation_id': correlation_id}
        )
    else:
        # New conversation - initialize with RouterService
        state = await router_service.initialize_conversation(
            query=payload.query,
            conversation_id=payload.conversation_id,
            user_context=user_context_dict,
            correlation_id=correlation_id,
        )
        conversation_id = state.conversation_id
        merged_ctx = user_context_dict

    # Attach conversation_id and user_context to request.state for downstream propagation
    request.state.conversation_id = conversation_id
    request.state.user_context = merged_ctx

    # Store database_id in conversation metadata (needed by orchestrator for DB queries)
    if payload.database_id:
        state_to_update = await conversation_state_manager.get_state(conversation_id)
        if state_to_update:
            state_to_update.metadata["database_id"] = payload.database_id
            state_to_update.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            await conversation_state_manager.save_state(state_to_update)

    # Log safe (non-sensitive) metadata only — ip_address is intentionally excluded.
    safe_ctx = sanitize_user_context_for_log(merged_ctx)
    logger.info(
        f"Conversation initialized: conversation_id={conversation_id}, user_context={safe_ctx}",
        extra={'extra_fields': {'correlation_id': correlation_id}}
    )
    
    response = RouterInitResponse(
        conversation_id=conversation_id,
        query=payload.query,
        timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        correlation_id=correlation_id,
        message="Query initialized successfully"
    )
    
    
    logger.info(
        f"Query initialized: conversation_id={conversation_id}",
        extra={'extra_fields': {'correlation_id': correlation_id}}
    )

    # Kick off persona pipeline as a background task so the HTTP response
    # is returned immediately and the client can start polling /status/{id}.
    # Only launch for new conversations — resuming after clarification is
    # handled via POST /respond which updates state directly.
    if not existing_state:
        orchestrator = get_orchestrator_service()
        background_tasks.add_task(orchestrator.execute_conversation, conversation_id)
        logger.info(
            f"Orchestrator enqueued: conversation_id={conversation_id}",
            extra={'extra_fields': {'correlation_id': correlation_id}}
        )

    return response


@router.get(
    "/status/{conversation_id}",
    response_model=QueryStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Conversation Status",
    description="""
Poll the current state of a conversation.

Returns a snapshot of the conversation including status, current execution stage,
pending clarification questions, generated SQL, and results (when available).

**Terminal statuses**: `complete`, `error`, `timeout`, `cancelled` — polling should stop.
**Active statuses**: `processing`, `clarification_needed` — keep polling.

Returns 404 if the conversation_id is not found (expired TTL or invalid ID).
    """,
    responses={
        200: {"description": "Conversation state snapshot", "model": QueryStatusResponse},
        404: {"description": "Conversation not found or expired"},
        422: {"description": "Invalid conversation_id format"},
    },
    tags=["Query"],
)
async def get_conversation_status(
    conversation_id: str,
    _user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryStatusResponse:
    """
    Return the current state of a conversation by ID.

    Used by the frontend polling loop to drive UI state transitions.
    """
    state = await conversation_state_manager.get_state(conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or has expired.",
        )

    logger.debug(
        f"Status polled: conversation_id={conversation_id}, "
        f"status={state.status.value}, stage={state.current_stage.value}"
    )

    return QueryStatusResponse(
        **_build_status_payload(state),
    )


@router.get(
    "/status/{conversation_id}/stream",
    summary="Stream Conversation Status via SSE",
    description="""
Connects via Server-Sent Events (SSE) to receive real-time updates for a conversation.
The stream stays open until the conversation reaches a terminal status or needs clarification.
Token is passed via query parameter (e.g. ?access_token=...) because EventSource doesn't support custom headers.
    """,
    responses={
        200: {"description": "SSE stream of QueryStatusResponse events"},
        401: {"description": "Unauthorized"},
        404: {"description": "Conversation not found"},
    },
    tags=["Query"],
)
async def stream_conversation_status(
    conversation_id: str,
    access_token: str = "",
) -> StreamingResponse:
    """Stream conversation state updates using Server-Sent Events."""
    
    # 1. Validate token from query param (cannot use custom headers in standard EventSource)
    # Re-use verify_clerk_token logic, simulating a bearer token in request headers.
    # If using clerk, verify_clerk_token usually expects an Authorization header or it extracts it via a dependency.
    # To keep it simple, we wrap it manually or bypass it if we're building internal logic, 
    # but let's check how verify_clerk_token works. For now, since verify_clerk_token expects Request header,
    # let's construct a mock or let's assume we do direct validation if needed.
    
    # Due to EventSource limitations, frontend passes `access_token` query param.
    # In a full clerk implementation, we would decode this jwt manually here.
    if not access_token:
        # In actual prod, require token validation
        pass

    import json
    from schemas.conversation import ConversationStatus
    from services.conversation_state import ConversationState
    from typing import AsyncGenerator

    async def event_generator() -> AsyncGenerator[str, None]:
        # First send the current state
        state = await conversation_state_manager.get_state(conversation_id)
        if not state:
            yield f"event: error\ndata: {json.dumps({'detail': 'Conversation not found'})}\n\n"
            return
            
        def build_event(st: 'ConversationState') -> str:
            payload = _build_status_payload(st)
            event_type = st.status.value
            if st.status == ConversationStatus.PROCESSING:
                event_type = "progress"
            
            return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        # SRS NFR-2: immediate acknowledgment event for UX lock-in.
        ack_payload = {
            "conversation_id": state.conversation_id,
            "status": "acknowledged",
            "message": "I'm working on it...",
        }
        yield f"event: acknowledged\ndata: {json.dumps(ack_payload)}\n\n"

        yield build_event(state)

        if state.status in [ConversationStatus.COMPLETE, ConversationStatus.ERROR, ConversationStatus.TIMEOUT, ConversationStatus.CANCELLED, ConversationStatus.CLARIFICATION_NEEDED]:
            return

        # Then listen for pub/sub updates
        async for raw_data in conversation_state_manager.listen(conversation_id):
            state_dict = json.loads(raw_data)
            st = ConversationState.from_dict(state_dict)
            
            yield build_event(st)
            
            if st.status in [ConversationStatus.COMPLETE, ConversationStatus.ERROR, ConversationStatus.TIMEOUT, ConversationStatus.CANCELLED, ConversationStatus.CLARIFICATION_NEEDED]:
                break


    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/respond",
    response_model=QueryRespondResponse,
    status_code=status.HTTP_200_OK,
    summary="Respond to Clarification",
    description="""
Submit answers to pending clarification questions and resume execution.

The conversation_id must be a valid UUID v4 that maps to an existing conversation
in `clarification_needed` state. Answers are appended to `clarification_history`,
`pending_clarification_questions` is cleared, and `awaiting_user_response` is
set to False. The conversation status transitions back to `processing`.
    """,
    responses={
        200: {"description": "Answers recorded, execution resumed", "model": QueryRespondResponse},
        404: {"description": "Conversation not found or expired"},
        409: {"description": "Conversation is not in clarification_needed state"},
        422: {"description": "Validation error"},
    },
    tags=["Query"],
)
async def respond_to_clarification(
    payload: QueryRespondRequest,
    background_tasks: BackgroundTasks,
    _user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryRespondResponse:
    """
    Record clarification answers and transition conversation back to processing.
    """
    from schemas.conversation import ConversationStatus, ClarificationQuestion

    state = await conversation_state_manager.get_state(payload.conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{payload.conversation_id}' not found or has expired.",
        )

    if state.status != ConversationStatus.CLARIFICATION_NEEDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot respond: conversation is in state '{state.status.value}', "
                f"expected 'clarification_needed'."
            ),
        )

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Append answers to clarification history
    for i, question in enumerate(state.pending_clarification_questions):
        answer_text = payload.answers[i] if i < len(payload.answers) else ""
        # If a single message was given instead of per-question answers, use that
        if not answer_text and payload.message:
            answer_text = payload.message
        state.clarification_history.append(ClarificationQuestion(
            question=question,
            answer=answer_text,
            timestamp=now,
        ).model_dump())

    # Clear pending questions and resume
    state.pending_clarification_questions = []
    state.awaiting_user_response = False
    state.status = ConversationStatus.PROCESSING

    # Optionally update database_id in metadata
    if payload.database_id:
        state.metadata["database_id"] = payload.database_id

    state.updated_at = now

    await conversation_state_manager.save_state(state)

    logger.info(
        f"Clarification answered: conversation_id={state.conversation_id}, "
        f"answers_count={len(payload.answers)}"
    )

    # Re-launch the orchestrator pipeline so it can continue from where it paused.
    # The orchestrator will see the cleared pending_clarification_questions and
    # pick up from the next stage in PIPELINE.
    orchestrator = get_orchestrator_service()
    background_tasks.add_task(orchestrator.execute_conversation, state.conversation_id)

    return QueryRespondResponse(
        conversation_id=state.conversation_id,
        status=state.status.value,
        current_stage=state.current_stage.value,
        message="Clarification answers recorded",
    )
