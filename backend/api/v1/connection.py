from fastapi import APIRouter, status, Request, Depends
from typing import Dict, Any
from schemas.connection import ConnectionRequest, ConnectionTestResponse, ConnectionErrorDetail
from services.db_connection_service import DBConnectionService
from exceptions import DatabaseConnectionError
from slowapi import Limiter
from slowapi.util import get_remote_address
from config import settings
from utils.auth import verify_clerk_token

router = APIRouter()

# Initialize limiter for this router
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/test-connection",
    response_model=ConnectionTestResponse,
    status_code=status.HTTP_200_OK,
    summary="Test Database Connection (Authentication Required)",
    description="""
Test the validity and reachability of a PostgreSQL database connection.

**Authentication Required:** This endpoint requires a valid Clerk JWT token in the Authorization header.

This endpoint performs a lightweight connection check without fetching any database metadata.

**Connection URL Format:**
`postgresql://username:password@host:port/database`

**Authentication:**
- **Header Required:** `Authorization: Bearer <clerk_jwt_token>`
- Tokens are issued by Clerk after user sign-in
- Tokens are automatically included by the frontend (@clerk/clerk-react)

**Checks Performed:**
1. JWT token verification (user authentication)
2. URL structure validation (scheme, host, port, database name)
3. Actual connection attempt to the database server

**Error Scenarios:**
- Missing or invalid JWT token (status: 401)
- Invalid URL format (error_code: INVALID_URL)
- Authentication failure (error_code: AUTH_FAILED)
- Database not found (error_code: DATABASE_NOT_FOUND)
- Host unreachable or network issues (error_code: HOST_UNREACHABLE)
- Connection timeout (error_code: TIMEOUT)
- SSL/TLS certificate errors (error_code: SSL_ERROR)
    """,
    responses={
        200: {
            "description": "Connection successful",
            "model": ConnectionTestResponse
        },
        401: {
            "description": "Unauthorized - missing or invalid JWT token",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Authentication required. Please provide a valid access token."
                    }
                }
            }
        },
        400: {
            "description": "Connection failed - validation error or connection error",
            "model": ConnectionErrorDetail
        },
        422: {
            "description": "Invalid request body"
        }
    },
    operation_id="test_database_connection",
    tags=["Connection"]
)
# Note: Rate limiting is applied but tests use RATE_LIMIT_ENABLED=False
@limiter.limit(f"{settings.rate_limit_per_minute}/minute" if settings.rate_limit_enabled else "1000000/minute")
async def test_connection(
    request: Request, 
    body: ConnectionRequest,
    user_claims: Dict[str, Any] = Depends(verify_clerk_token)
) -> ConnectionTestResponse:
    """
    Test the validity and reachability of a PostgreSQL connection URL.
    
    Requires user authentication via Clerk JWT token.
    
    Args:
        request: FastAPI Request object (required by rate limiter)
        body: ConnectionRequest containing the PostgreSQL connection URL
        user_claims: JWT claims from authenticated user (injected by verify_clerk_token dependency)
        
    Returns:
        ConnectionTestResponse with status and message on success
        
    Raises:
        HTTPException: 401 if JWT token is missing/invalid
        HTTPException: 400 if URL validation fails or connection cannot be established
    """
    # Log authenticated request (user_id from JWT)
    user_id = user_claims.get("sub", "unknown")
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Connection test requested by user: {user_id[:8]}...")
    
    # Initialize service with default dependencies (production configuration)
    db_service = DBConnectionService()
    
    # 1. Structural Validation
    validation_result = db_service.parse_and_verify_url(body.connection_url)
    if not validation_result.success:
        raise DatabaseConnectionError(
            detail=validation_result.message,
            error_code=validation_result.error_code
        )

    # 2. Connection Test (one-shot, no pooling)
    connection_result = await db_service.test_connection_oneshot(body.connection_url)
    
    if connection_result.success:
        return ConnectionTestResponse(
            status="success", 
            message=connection_result.message
        )
    else:
        # For connection failures, raise DatabaseConnectionError with structured error details
        raise DatabaseConnectionError(
            detail=connection_result.message,
            error_code=connection_result.error_code
        )
