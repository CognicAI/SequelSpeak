from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.v1 import connection, health
from exceptions import DatabaseConnectionError
from config import settings
import logging
from contextlib import asynccontextmanager
from logging_config import setup_logging
import uuid
from contextvars import ContextVar
import time
from services.connection_pool import pool_manager

# Initialize logging before anything else
setup_logging()
logger = logging.getLogger(__name__)

# Context variable for correlation ID (used by logging middleware)
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default=None)

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
    logger.info(f"Pool Config: min={settings.db_pool_min_size}, max={settings.db_pool_max_size}, timeout={settings.db_pool_timeout}s")
    
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
    logger.info("✓ Connection pool manager initialized")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown: Close all connection pools gracefully
    logger.info("=" * 60)
    logger.info("Shutting down SequelSpeak Backend")
    logger.info("=" * 60)
    await pool_manager.close_all()
    logger.info("✓ Shutdown complete")
    logger.info("=" * 60)

app = FastAPI(
    title="SequelSpeak Backend API",
    description="""
## SequelSpeak Backend API

Natural language SQL query interface with PostgreSQL connection management.

### Features
- **Database Connection**: Secure PostgreSQL connection with validation
- **Health Monitoring**: Real-time database connectivity status
- **Error Handling**: Structured error responses with actionable messages

### Authentication
Currently, this API does not require authentication. Database credentials are passed per-request.
    """,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "Health check endpoints for monitoring API and database connectivity."
        },
        {
            "name": "Connection",
            "description": "Database connection testing and validation endpoints."
        }
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Middleware to add correlation ID to all requests for log tracing.
    
    Correlation ID is either extracted from X-Correlation-ID header (if provided)
    or generated as a new UUID. The ID is:
    - Added to response headers
    - Stored in context for logging
    - Used to trace related log entries
    """
    # Get or generate correlation ID
    correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
    
    # Store in context for logging
    correlation_id_var.set(correlation_id)
    
    # Log request with correlation ID
    start_time = time.time()
    logger.info(
        f"Request started: {request.method} {request.url.path}",
        extra={'extra_fields': {'correlation_id': correlation_id}}
    )
    
    # Process request
    response = await call_next(request)
    
    # Add correlation ID to response headers
    response.headers['X-Correlation-ID'] = correlation_id
    
    # Log response with timing
    duration = time.time() - start_time
    logger.info(
        f"Request completed: {request.method} {request.url.path} - "
        f"Status: {response.status_code} - Duration: {duration:.3f}s",
        extra={'extra_fields': {'correlation_id': correlation_id, 'duration_seconds': duration}}
    )
    
    return response


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



app.include_router(connection.router, prefix="/api/v1/utils")
app.include_router(health.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"status": "ok"}
