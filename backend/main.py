from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.v1 import connection
from exceptions import DatabaseConnectionError

app = FastAPI(title="Backend API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseConnectionError)
async def database_connection_error_handler(request: Request, exc: DatabaseConnectionError):
    """
    Custom exception handler for DatabaseConnectionError.
    
    Converts DatabaseConnectionError exceptions into properly validated JSONResponse
    objects that match the ConnectionErrorDetail schema.
    
    Args:
        request: The incoming request
        exc: The ConnectionError exception
        
    Returns:
        JSONResponse with structured error details
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": exc.error_code.value if exc.error_code else None
        }
    )



app.include_router(connection.router, prefix="/api/v1/utils", tags=["Utils"])

@app.get("/")
async def root():
    return {"status": "ok"}
