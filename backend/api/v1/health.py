from fastapi import APIRouter, status
from schemas.health import HealthResponse, DatabaseStatus

router = APIRouter()

@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get System Health",
    description="Reports the overall system and database connectivity status. Currently returning mock data as per the parallel development contract.",
    tags=["Health"]
)
async def get_health() -> HealthResponse:
    """
    Returns the system health status.
    
    This is a mock implementation for parallel development.
    The database state is hardcoded to 'connected: true'.
    """
    return HealthResponse(
        status="UP",
        database=DatabaseStatus(connected=True)
    )
