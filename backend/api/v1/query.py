"""
Query Router API Endpoint

Handles incoming natural language queries and validates them against
the Router request schema. This is the entry point for all query requests.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, status, Request, Depends
from pydantic import ValidationError
from schemas.router import (
    RouterRequest,
    RouterInitResponse,
    RouterErrorResponse,
    RouterErrorCode,
    UserContext,
)
from services.conversation_state import conversation_state_manager
from services.router_service import get_router_service
from utils.auth import verify_clerk_token
from utils.security import sanitize_user_context_for_log

router = APIRouter()
logger = logging.getLogger(__name__)


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
    "/query",
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
    # - Auto-populate ip_address from the real client IP if the caller did not supply it.
    user_context: UserContext = payload.user_context if payload.user_context is not None else UserContext()
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
    
    return response

