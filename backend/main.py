from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.v1 import connection, health
from exceptions import DatabaseConnectionError
from config import settings
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Validate configuration on startup and log system info.
    Configuration validation already happened during module import (config.py),
    but we log the results here for visibility.
    """
    logger.info("=" * 60)
    logger.info("Starting SequelSpeak Backend")
    logger.info("=" * 60)
    logger.info(f"App Name: {settings.app_name}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"DB Timeout: {settings.db_connection_timeout}s")
    
    # Log CORS config (mask if production)
    origins = settings.get_allowed_origins_list()
    if settings.environment == "production" and "*" in origins:
        logger.warning("⚠️  CORS wildcard (*) detected in PRODUCTION - security risk!")
    logger.info(f"CORS Origins: {origins}")
    
    # Log secret key status (never log the actual key)
    if settings.secret_key:
        logger.info(f"Secret Key: configured ({len(settings.secret_key)} chars)")
    else:
        logger.info("Secret Key: not set (acceptable for development)")
    
    logger.info("=" * 60)
    logger.info("✓ Configuration validated successfully")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown logic (if any) goes here
    pass

app = FastAPI(title="SequelSpeak Backend API", lifespan=lifespan)

# Configure CORS from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
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
        exc: The DatabaseConnectionError exception
        
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
app.include_router(health.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"status": "ok"}
