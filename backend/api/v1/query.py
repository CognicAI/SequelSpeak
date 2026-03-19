"""
Query Router API Endpoint

Handles incoming natural language queries and validates them against
the Router request schema. This is the entry point for all query requests.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, cast
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
    QueryCancelResponse,
    QueryRetryResponse,
)
from services.conversation_state import conversation_state_manager, ConversationState
from services.router_service import get_router_service
from schemas.conversation import InvalidStateTransition, QueryType
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


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge dictionaries without mutating inputs."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            nested_base = cast(dict[str, Any], result[key])
            nested_override = cast(dict[str, Any], value)
            result[key] = _deep_merge_dicts(nested_base, nested_override)
        else:
            result[key] = value
    return result


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
        "clarification_rounds": state.clarification_rounds,
        "awaiting_user_response": state.awaiting_user_response,
        "pending_clarification_questions": list(state.pending_clarification_questions or []),
        "generated_sql": state.generated_sql,
        "execution_result": state.execution_result,
        "explanation": state.explanation,
        "persona_trace": _to_persona_trace(state.persona_trace or []),
    }
    return payload


def _state_owner_user_id(state: ConversationState) -> Optional[str]:
    """Extract conversation owner user_id from persisted state metadata."""
    user_context = state.metadata.get("user_context", {})
    user_id = user_context.get("user_id")
    return str(user_id) if user_id is not None else None


def _assert_conversation_owner(state: ConversationState, user_id: str, conversation_id: str) -> None:
    """Ensure only the conversation owner can access or mutate a conversation."""
    owner_user_id = _state_owner_user_id(state)
    if owner_user_id is None or owner_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Conversation '{conversation_id}' is not accessible by this user.",
        )


def _check_clarification_timeout(state: ConversationState) -> bool:
    """
    FR-82: Check if a paused conversation has exceeded the 30-minute timeout.

    Returns True if the conversation has timed out, False otherwise.
    """
    from schemas.conversation import CLARIFICATION_TIMEOUT_SECONDS, ConversationStatus

    if state.status != ConversationStatus.CLARIFICATION_NEEDED:
        return False

    try:
        updated_at = datetime.fromisoformat(state.updated_at.replace('Z', '+00:00'))
        elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
        return elapsed > CLARIFICATION_TIMEOUT_SECONDS
    except (ValueError, TypeError):
        return False


def build_router_context(
    state: ConversationState,
    query_type: QueryType = QueryType.NEW,
) -> dict[str, Any]:
    """
    Build compact multi-turn context payload for Router consumption.
    
    Computed on-the-fly from state.turns (never persisted).
    Context is gated by query_type:
      - FOLLOW_UP: include last 3 turns for continuity
      - NEW: empty history (no noise from unrelated prior turns)
    """
    # Gate context by query type
    if query_type == QueryType.NEW:
        relevant_turns: list[dict[str, Any]] = []
    else:
        # FOLLOW_UP / CLARIFICATION_RESPONSE: include recent turns
        relevant_turns = list(state.turns[-3:]) if state.turns else []
    
    last_successful_query: Optional[str] = None
    last_sql: Optional[str] = None
    for turn in reversed(relevant_turns):
        if turn.get('status') == 'complete':
            q = turn.get('original_query')
            s = turn.get('generated_sql')
            last_successful_query = str(q) if isinstance(q, str) else None
            last_sql = str(s) if isinstance(s, str) else None
            break
    
    return {
        'previous_queries': relevant_turns,
        'last_successful_query': last_successful_query,
        'last_sql': last_sql,
        'clarification_history': list(state.clarification_history or []),
    }


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
        if existing_state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation '{payload.conversation_id}' not found or has expired.",
            )

        _assert_conversation_owner(existing_state, user_id, payload.conversation_id)
    
    should_enqueue = False
    if existing_state:
        # ── Existing conversation ──────────────────────────────────────
        conversation_id = existing_state.conversation_id
        
        from schemas.conversation import ConversationStatus, ExecutionStage

        # FR-82: Check for clarification timeout
        if _check_clarification_timeout(existing_state):
            existing_state.status = ConversationStatus.TIMEOUT
            existing_state.current_stage = ExecutionStage.TIMEOUT
            existing_state.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            await conversation_state_manager.save_state(existing_state)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=(
                    f"Conversation '{existing_state.conversation_id}' timed out after "
                    "30 minutes of inactivity during clarification."
                ),
            )

        # Deep-merge user context (Issue #10)
        existing_ctx = existing_state.metadata.get("user_context", {})
        new_ctx = {k: v for k, v in user_context_dict.items() if v is not None}
        merged_ctx: dict[str, Any] = _deep_merge_dicts(existing_ctx, new_ctx)
        existing_state.metadata["user_context"] = merged_ctx
        # Preserve original correlation_id; only update if not already set
        if not existing_state.metadata.get("correlation_id"):
            existing_state.metadata["correlation_id"] = correlation_id
        
        # Block if already processing or awaiting clarification
        if existing_state.status == ConversationStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Query already in progress. Please wait or cancel.",
            )
        if existing_state.status == ConversationStatus.CLARIFICATION_NEEDED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conversation '{existing_state.conversation_id}' is awaiting clarification. "
                    "Use /api/v1/query/respond to continue."
                ),
            )
        
        # Validate state transition (Issue #6)
        try:
            existing_state.transition_status(ConversationStatus.PROCESSING)
        except InvalidStateTransition as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        
        # Classify query and start new turn (Issues #1, #2, #5)
        query_type = router_service.classify_query(payload.query, existing_state)
        existing_state.start_new_turn(payload.query, query_type)
        existing_state.current_stage = ExecutionStage.PLANNING
        
        should_enqueue = True
        # Set database_id BEFORE save to avoid extra roundtrip
        if payload.database_id:
            existing_state.metadata["database_id"] = payload.database_id
        existing_state.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        await conversation_state_manager.save_state(existing_state)
    else:
        # ── New conversation ───────────────────────────────────────────
        state = await router_service.initialize_conversation(
            query=payload.query,
            conversation_id=None,
            user_context=user_context_dict,
            correlation_id=correlation_id,
        )
        conversation_id = state.conversation_id
        # Set database_id BEFORE first save to avoid extra roundtrip
        if payload.database_id:
            state.metadata["database_id"] = payload.database_id
        await conversation_state_manager.save_state(state)
        merged_ctx = user_context_dict
        should_enqueue = True

    # Attach to request.state for downstream propagation
    request.state.conversation_id = conversation_id
    request.state.user_context = merged_ctx

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

    if should_enqueue:
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
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryStatusResponse:
    """
    Return the current state of a conversation by ID.

    Used by the frontend polling loop to drive UI state transitions.
    """
    user_id = str(user_claims.get("sub", "unknown"))
    state = await conversation_state_manager.get_state(conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or has expired.",
        )

    _assert_conversation_owner(state, user_id, conversation_id)

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
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> StreamingResponse:
    """Stream conversation state updates using Server-Sent Events."""
    user_id = str(user_claims.get("sub", "unknown"))

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

        _assert_conversation_owner(state, user_id, conversation_id)
            
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
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryRespondResponse:
    """
    Record clarification answers and transition conversation back to processing.
    
    Validates answer count matches pending questions (Issue #7),
    refines current_nl_query from Q&A (Issue #3), and uses
    validated state transition (Issue #6).
    """
    from schemas.conversation import ConversationStatus, ClarificationQuestion, ExecutionStage
    user_id = str(user_claims.get("sub", "unknown"))

    state = await conversation_state_manager.get_state(payload.conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{payload.conversation_id}' not found or has expired.",
        )

    _assert_conversation_owner(state, user_id, payload.conversation_id)

    # FR-82: Check for clarification timeout before processing
    if _check_clarification_timeout(state):
        state.status = ConversationStatus.TIMEOUT
        state.current_stage = ExecutionStage.TIMEOUT
        state.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        await conversation_state_manager.save_state(state)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"Conversation '{payload.conversation_id}' timed out after "
                "30 minutes of inactivity during clarification."
            ),
        )

    if state.status != ConversationStatus.CLARIFICATION_NEEDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot respond: conversation is in state '{state.status.value}', "
                f"expected 'clarification_needed'."
            ),
        )

    # FR-87: Enforce clarification round limit
    from schemas.conversation import MAX_CLARIFICATION_ROUNDS
    state.clarification_rounds += 1
    if state.clarification_rounds > MAX_CLARIFICATION_ROUNDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Maximum clarification rounds ({MAX_CLARIFICATION_ROUNDS}) exceeded. "
                "Please try rephrasing your query, use the manual SQL editor, "
                "or check similar past queries for guidance."
            ),
        )

    # ── Validate answer count (Issue #7) ───────────────────────────
    pending_count = len(state.pending_clarification_questions)
    answer_count = len(payload.answers)
    # Allow free-form message as fallback for all questions
    if answer_count == 0 and payload.message:
        # Single message used as answer for all questions
        pass
    elif answer_count == 0 and not payload.message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Must provide either 'answers' array or 'message' field.",
        )
    elif answer_count != pending_count and answer_count > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Answer count mismatch: got {answer_count} answers "
                f"but {pending_count} questions are pending. "
                f"Provide exactly {pending_count} answers or use the 'message' field."
            ),
        )

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Build Q&A pairs and append to clarification history
    # FR-81 compat: questions may be plain strings or structured dicts
    q_and_a_pairs: list[dict[str, str]] = []
    for i, question_item in enumerate(state.pending_clarification_questions):
        # Extract question text from string or structured dict
        if isinstance(question_item, dict):
            question_dict = cast(Mapping[str, Any], question_item)
            question_text = str(question_dict.get('question', question_item))
        else:
            question_text = str(question_item)
        answer_text = payload.answers[i] if i < len(payload.answers) else ""
        if not answer_text and payload.message:
            answer_text = payload.message
        q_and_a_pairs.append({'question': question_text, 'answer': answer_text})
        state.clarification_history.append(ClarificationQuestion(
            question=question_text,
            answer=answer_text,
            timestamp=now,
        ).model_dump())

    # ── Refine query from Q&A (Issue #3) ───────────────────────────
    state.refine_query_after_clarification(q_and_a_pairs)

    # ── Validated status transition (Issue #6) ─────────────────────
    state.pending_clarification_questions = []
    state.awaiting_user_response = False
    try:
        state.transition_status(ConversationStatus.PROCESSING)
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    # FR-78/FR-86: Resume from paused_at_stage if available
    paused_at = state.metadata.get('_paused_at_stage')
    if paused_at:
        try:
            state.current_stage = ExecutionStage(paused_at)
        except ValueError:
            state.current_stage = ExecutionStage.PLANNING
        # Clear the paused marker
        state.metadata.pop('_paused_at_stage', None)
    else:
        state.current_stage = ExecutionStage.PLANNING

    if payload.database_id:
        state.metadata["database_id"] = payload.database_id

    state.updated_at = now
    await conversation_state_manager.save_state(state)

    logger.info(
        f"Clarification answered: conversation_id={state.conversation_id}, "
        f"answers_count={len(payload.answers)}, "
        f"refined_query='{(state.current_nl_query or '')[:80]}', "
        f"resume_stage={state.current_stage.value}"
    )

    # Re-launch orchestrator — resumes from paused_at_stage
    orchestrator = get_orchestrator_service()
    background_tasks.add_task(orchestrator.execute_conversation, state.conversation_id)

    return QueryRespondResponse(
        conversation_id=state.conversation_id,
        status=state.status.value,
        current_stage=state.current_stage.value,
        message="Clarification answers recorded",
    )


# ──────────────────────────────────────────────────────────────────────────────
# FR-83: Cancel endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/cancel/{conversation_id}",
    response_model=QueryCancelResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a Query",
    description="""
Cancel an active or paused conversation. Transitions the conversation to
`cancelled` status. Only the conversation owner may cancel.

Safe to call on already-cancelled conversations (idempotent).

Terminal states (`complete`, `error`, `timeout`) cannot be cancelled.
    """,
    responses={
        200: {"description": "Conversation cancelled", "model": QueryCancelResponse},
        403: {"description": "Not the conversation owner"},
        404: {"description": "Conversation not found"},
        409: {"description": "Conversation is in a terminal state and cannot be cancelled"},
    },
    tags=["Query"],
)
async def cancel_query(
    conversation_id: str,
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryCancelResponse:
    """Cancel an active or paused conversation (FR-83)."""
    from schemas.conversation import ConversationStatus, ExecutionStage

    user_id = str(user_claims.get("sub", "unknown"))
    state = await conversation_state_manager.get_state(conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or has expired.",
        )

    _assert_conversation_owner(state, user_id, conversation_id)

    # Idempotent: already cancelled is fine
    if state.status == ConversationStatus.CANCELLED:
        return QueryCancelResponse(
            conversation_id=conversation_id,
            status="cancelled",
            message="Conversation was already cancelled",
        )

    # Cannot cancel terminal states
    terminal_states = {ConversationStatus.COMPLETE, ConversationStatus.ERROR, ConversationStatus.TIMEOUT}
    if state.status in terminal_states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot cancel: conversation is in terminal state '{state.status.value}'."
            ),
        )

    # Transition to cancelled
    try:
        state.transition_status(ConversationStatus.CANCELLED)
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    state.current_stage = ExecutionStage.CANCELLED
    state.awaiting_user_response = False
    state.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    await conversation_state_manager.save_state(state)

    logger.info(
        f"Conversation cancelled: conversation_id={conversation_id}, user_id={user_id[:8]}..."
    )

    return QueryCancelResponse(
        conversation_id=conversation_id,
        status="cancelled",
        message="Conversation cancelled successfully",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Retry endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/retry/{conversation_id}",
    response_model=QueryRetryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a Failed Query",
    description="""
Retry a failed query by resetting the conversation to `processing` status
and re-enqueuing the orchestrator pipeline from the `planning` stage.

Only conversations in `error` status can be retried.
    """,
    responses={
        200: {"description": "Query retry initiated", "model": QueryRetryResponse},
        403: {"description": "Not the conversation owner"},
        404: {"description": "Conversation not found"},
        409: {"description": "Conversation is not in error state"},
    },
    tags=["Query"],
)
async def retry_query(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    user_claims: Dict[str, Any] = Depends(verify_clerk_token),
) -> QueryRetryResponse:
    """Retry a failed query by re-enqueuing the orchestrator pipeline."""
    from schemas.conversation import ConversationStatus, ExecutionStage

    user_id = str(user_claims.get("sub", "unknown"))
    state = await conversation_state_manager.get_state(conversation_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or has expired.",
        )

    _assert_conversation_owner(state, user_id, conversation_id)

    if state.status != ConversationStatus.ERROR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot retry: conversation is in state '{state.status.value}', "
                f"expected 'error'."
            ),
        )

    # Transition back to processing
    try:
        state.transition_status(ConversationStatus.PROCESSING)
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    state.current_stage = ExecutionStage.PLANNING
    state.errors = []  # Clear errors for retry
    state.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    await conversation_state_manager.save_state(state)

    # Re-enqueue orchestrator
    orchestrator = get_orchestrator_service()
    background_tasks.add_task(orchestrator.execute_conversation, conversation_id)

    logger.info(
        f"Query retry initiated: conversation_id={conversation_id}, user_id={user_id[:8]}..."
    )

    return QueryRetryResponse(
        conversation_id=conversation_id,
        status=state.status.value,
        current_stage=state.current_stage.value,
        message="Query retry initiated",
    )
