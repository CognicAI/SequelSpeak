from fastapi import APIRouter, HTTPException
from schemas.connection import ConnectionRequest
from services.db_connection_service import DBConnectionService

router = APIRouter()

@router.post("/test-connection")
async def test_connection(request: ConnectionRequest):
    """
    Test the validity and reachability of a PostgreSQL connection URL.
    """
    # 1. Structural Validation
    validation_result = DBConnectionService.parse_and_verify_url(request.connection_url)
    if not validation_result["valid"]:
        raise HTTPException(status_code=400, detail=validation_result["message"])

    # 2. Connection Test
    connection_result = DBConnectionService.test_connection(request.connection_url)
    
    if connection_result["success"]:
        return {"status": "success", "message": connection_result["message"]}
    else:
        # We return 200 even for connection failure to distinguish from API errors, 
        # but with status=error in valid JSON response, or we could use 400. 
        # Let's stick to returning a structured response.
        raise HTTPException(status_code=400, detail=connection_result["message"])
