from fastapi import APIRouter, status
from schemas.connection import ConnectionRequest, ConnectionTestResponse, ConnectionErrorDetail
from services.db_connection_service import DBConnectionService
from exceptions import ConnectionError

router = APIRouter()


@router.post(
    "/test-connection",
    response_model=ConnectionTestResponse,
    status_code=status.HTTP_200_OK,
    summary="Test Database Connection",
    description="""
Test the validity and reachability of a PostgreSQL database connection.

This endpoint performs a lightweight connection check without fetching any database metadata.

**Connection URL Format:**
`postgresql://username:password@host:port/database`

**Checks Performed:**
1. URL structure validation (scheme, host, port, database name)
2. Actual connection attempt to the database server

**Error Scenarios:**
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
async def test_connection(request: ConnectionRequest) -> ConnectionTestResponse:
    """
    Test the validity and reachability of a PostgreSQL connection URL.
    
    Args:
        request: ConnectionRequest containing the PostgreSQL connection URL
        
    Returns:
        ConnectionTestResponse with status and message on success
        
    Raises:
        HTTPException: 400 error if URL validation fails or connection cannot be established
    """
    # 1. Structural Validation
    validation_result = DBConnectionService.parse_and_verify_url(request.connection_url)
    if not validation_result.success:
        raise ConnectionError(
            detail=validation_result.message,
            error_code=validation_result.error_code
        )

    # 2. Connection Test
    connection_result = DBConnectionService.test_connection(request.connection_url)
    
    if connection_result.success:
        return ConnectionTestResponse(
            status="success", 
            message=connection_result.message
        )
    else:
        # For connection failures, raise ConnectionError with structured error details
        raise ConnectionError(
            detail=connection_result.message,
            error_code=connection_result.error_code
        )
