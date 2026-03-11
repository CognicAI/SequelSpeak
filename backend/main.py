from fastapi import FastAPI, Request, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from api.v1 import connection, health, meta, query, profiles
from exceptions import DatabaseConnectionError
from schemas.router import RouterErrorResponse, RouterErrorCode
from utils.security import mask_connection_url
from config import settings
import logging
from contextlib import asynccontextmanager
from logging_config import setup_logging
import uuid
from contextvars import ContextVar
import time
import asyncio
from typing import Callable, Awaitable, Any
from services.connection_pool import pool_manager
from services.conversation_state import conversation_state_manager
from services.router_service import initialize_router_service
from services.profile_service import profile_service
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize logging before anything else
setup_logging()
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # No global limits, apply per-endpoint
    enabled=settings.rate_limit_enabled,
    storage_uri="memory://"  # In-memory storage for rate limits
)

# Context variable for correlation ID (used by logging middleware)
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')

# Import Prometheus metrics if enabled
if settings.metrics_enabled:
    from utils import prometheus as prom_metrics
else:
    prom_metrics = None

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
    logger.info(f"App Version: {settings.app_version}")
    logger.info(f"DB Timeout: {settings.db_connection_timeout}s")
    logger.info(f"Pool Config: min={settings.db_pool_min_size}, max={settings.db_pool_max_size}, timeout={settings.db_pool_timeout}s")
    logger.info(f"Metrics Enabled: {settings.metrics_enabled}")
    
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
    
    # Initialize Prometheus metrics
    if settings.metrics_enabled and prom_metrics:
        prom_metrics.initialize_metrics()
        logger.info("✓ Prometheus metrics initialized")
    
    # Initialize conversation state manager
    await conversation_state_manager.initialize()
    logger.info(f"✓ Conversation state manager initialized (mode: {conversation_state_manager.storage_mode})")
    
    # Initialize router service
    initialize_router_service(conversation_state_manager)
    logger.info("✓ Router service initialized")
    
    # Initialize profile service
    await profile_service.initialize()
    logger.info("✓ Profile service initialized")
    
    logger.info("=" * 60)
    logger.info("✓ Configuration validated successfully")
    logger.info("✓ Connection pool manager initialized")
    logger.info("=" * 60)
    
    # Start background task to update connection pool metrics
    metrics_task = None
    if settings.metrics_enabled and prom_metrics:
        async def update_pool_metrics_periodically():
            """Background task to update connection pool metrics every 10 seconds."""
            while True:
                try:
                    await asyncio.sleep(10)
                    await prom_metrics.update_connection_pool_metrics()
                except asyncio.CancelledError:
                    logger.info("Metrics update task cancelled")
                    break
                except Exception as e:
                    logger.warning(f"Error updating pool metrics: {e}")
        
        metrics_task = asyncio.create_task(update_pool_metrics_periodically())
        logger.info("✓ Metrics background task started")
    
    yield
    
    # Shutdown: Cancel metrics task and close all connection pools gracefully
    logger.info("=" * 60)
    logger.info("Shutting down SequelSpeak Backend")
    logger.info("=" * 60)
    
    if metrics_task:
        metrics_task.cancel()
        try:
            await metrics_task
        except asyncio.CancelledError:
            pass
        logger.info("✓ Metrics task stopped")
    
    await conversation_state_manager.close()
    logger.info("✓ Conversation state manager closed")
    
    await pool_manager.close_all()
    logger.info("✓ Shutdown complete")
    
    await profile_service.close()
    logger.info("✓ Profile service closed")
    logger.info("=" * 60)

app = FastAPI(
    title="SequelSpeak Backend API",
    description="""
## SequelSpeak Backend API

Natural language SQL query interface with PostgreSQL connection management.

### Features
- **User Authentication**: Clerk-based JWT authentication for API access
- **Database Connection**: Secure PostgreSQL connection with validation
- **Health Monitoring**: Real-time database connectivity status
- **Error Handling**: Structured error responses with actionable messages
- **Rate Limiting**: Protection against abuse and DoS attacks

### Security Model
This API uses a **dual authentication model**:

1. **User Authentication (Clerk JWT)**:
   - Required for API access to protected endpoints
   - JWT tokens are issued by Clerk after user sign-in
   - Tokens are automatically managed by the frontend (@clerk/clerk-react)
   - Validates user identity and session validity

2. **Database Authentication (PostgreSQL Credentials)**:
   - PostgreSQL credentials provided with each connection request
   - Validated directly against the target database
   - Credentials are never stored or cached on the server
   - Each user can connect to any database they have valid credentials for

**Security Features:**
- JWT token verification using Clerk's JWKS (JSON Web Key Set)
- Connection URLs are never logged (credentials are masked in all logs)
- Passwords are never stored or cached in backend or browser
- Input validation prevents SQL injection and command injection attacks
- Rate limiting protects against brute-force attempts (per-user when authenticated)
- Connection pooling is isolated per unique database URL
- Health check endpoints remain unauthenticated for monitoring tools
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
        },
        {
            "name": "Meta",
            "description": "API metadata, version information, and operational status."
        },
        {
            "name": "Profiles",
            "description": "CRUD operations for user database connection profiles."
        }
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add rate limiter state to app
app.state.limiter = limiter

# Add rate limit exceeded exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Configure CORS from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware to add correlation ID to all requests for log tracing.
    
    Correlation ID is either extracted from X-Correlation-ID header (if provided)
    or generated as a new UUID. The ID is:
    - Added to response headers
    - Stored in context for logging
    - Used to trace related log entries
    - Records Prometheus metrics
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
    
    # Record Prometheus metrics
    if settings.metrics_enabled and prom_metrics:
        try:
            # Use path template to avoid high-cardinality labels
            path_template = prom_metrics.extract_path_template(request.url.path)
            
            prom_metrics.http_requests_total.labels(
                method=request.method,
                endpoint=path_template,
                status=str(response.status_code)
            ).inc()
            
            prom_metrics.http_request_duration_seconds.labels(
                method=request.method,
                endpoint=path_template
            ).observe(duration)
        except Exception as e:
            # Don't let metrics collection break the application
            logger.warning(f"Failed to record metrics: {e}")
    
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
    # Track error in metrics
    if settings.metrics_enabled and prom_metrics and exc.error_code:
        prom_metrics.track_database_error(exc.error_code.value)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": exc.error_code.value if exc.error_code else None
        }
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle FastAPI RequestValidationError and convert to RouterErrorResponse format.
    
    This handler catches validation errors from request body validation (RouterRequest and other Pydantic models),
    converting them to structured error responses with appropriate error codes.
    
    Only intercepts validation errors from Pydantic model validators.
    JSON parsing errors and protocol-level errors are passed through as 422.
    
    Args:
        request: FastAPI Request object
        exc: FastAPI RequestValidationError (wraps Pydantic ValidationError)
        
    Returns:
        JSONResponse with RouterErrorResponse structure (400 Bad Request) for validation errors
        or JSONResponse with 422 for JSON/protocol errors
    """
    from api.v1.query import map_validation_error_to_router_error
    
    correlation_id = request.headers.get("X-Correlation-ID")
    errors = exc.errors()
    
    # Check if this is a JSON parsing error or protocol error (not a validation error)
    if errors and len(errors) > 0:
        first_error = errors[0]
        error_type = first_error.get("type", "")
        
        # JSON parsing errors, missing body, wrong content-type should remain 422
        if error_type in ["json_invalid", "missing", "json_type", "model_type", "model_attributes_type"]:
            # Convert errors to JSON-safe format (handle bytes, etc.)
            safe_errors: list[dict[str, Any]] = []
            for err in errors:
                safe_err = dict(err)
                # Convert bytes to string for JSON serialization
                if 'input' in safe_err and isinstance(safe_err['input'], bytes):
                    safe_err['input'] = safe_err['input'].decode('utf-8', errors='replace')
                safe_errors.append(safe_err)
            
            # Return FastAPI's default 422 response
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": safe_errors}
            )
    
    # This is a Pydantic validation error - convert to 400 with our error codes
    try:
        # Create a wrapper for our error mapping function
        class _FakeValidationError:
            """Temporary wrapper to make RequestValidationError compatible with our mapper"""
            def __init__(self, errors: list[Any]) -> None:
                self._errors = errors
            
            def errors(self) -> list[Any]:
                return self._errors
        
        fake_ve = _FakeValidationError(errors)  # type: ignore[arg-type]
        error_code, error_message = map_validation_error_to_router_error(fake_ve)  # type: ignore[arg-type]
    except Exception:
        # Fallback to generic error if mapping fails
        error_code = RouterErrorCode.INVALID_REQUEST
        error_message = "Request validation failed"
    
    # Sanitize error message (remove any sensitive data)
    sanitized_message = mask_connection_url(error_message)
    
    # Log the validation error
    logger.warning(
        f"Request validation failed: {error_code.value}",
        extra={'extra_fields': {
            'correlation_id': correlation_id,
            'error_code': error_code.value
        }}
    )
    
    # Return structured error response
    error_response = RouterErrorResponse(
        detail=sanitized_message,
        error_code=error_code
    )
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_response.model_dump()
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle Pydantic validation errors and convert to RouterErrorResponse format.
    
    This handler catches validation errors from RouterRequest and other Pydantic models,
    converting them to structured error responses with appropriate error codes.
    
    Args:
        request: FastAPI Request object
        exc: Pydantic ValidationError
        
    Returns:
        JSONResponse with RouterErrorResponse structure (400 Bad Request)
    """
    from api.v1.query import map_validation_error_to_router_error
    
    correlation_id = request.headers.get("X-Correlation-ID")
    
    # Map validation error to router error code
    error_code, error_message = map_validation_error_to_router_error(exc)
    
    # Sanitize error message (remove any sensitive data)
    sanitized_message = mask_connection_url(error_message)
    
    # Log the validation error
    logger.warning(
        f"Request validation failed: {error_code.value}",
        extra={'extra_fields': {
            'correlation_id': correlation_id,
            'error_code': error_code.value
        }}
    )
    
    # Return structured error response
    error_response = RouterErrorResponse(
        detail=sanitized_message,
        error_code=error_code
    )
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_response.model_dump()
    )



# API v1 routes
app.include_router(connection.router, prefix="/api/v1/utils", tags=["Connection"])
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(meta.router, prefix="/api/v1", tags=["Meta"])
app.include_router(query.router, prefix="/api/v1", tags=["Query"])
app.include_router(profiles.router, prefix="/api/v1", tags=["Profiles"])

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/metrics", response_class=PlainTextResponse, tags=["Monitoring"], include_in_schema=True)
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Exposes application metrics in Prometheus text exposition format for scraping
    by Prometheus or compatible monitoring systems.
    
    **Available Metrics:**
    
    - `sequelspeak_info`: Application information (version, environment, name)
    - `http_requests_total`: Total HTTP requests (labels: method, endpoint, status)
    - `http_request_duration_seconds`: HTTP request latency histogram (labels: method, endpoint)
    - `http_requests_in_progress`: Currently processing HTTP requests (labels: method, endpoint)
    - `active_database_connections`: Active database connections across all pools
    - `database_connection_pools_total`: Total number of connection pools
    - `database_errors_total`: Total database errors (labels: error_code)
    
    **Usage:**
    
    Configure Prometheus to scrape this endpoint:
    ```yaml
    scrape_configs:
      - job_name: 'sequelspeak'
        static_configs:
          - targets: ['localhost:8000']
    ```
    
    **Security:**
    
    This endpoint is unauthenticated by design for Prometheus scraping.
    Use network-level security (firewall rules, VPC) to restrict access in production.
    
    Returns:
        Prometheus metrics in text exposition format
    """
    if not settings.metrics_enabled or not prom_metrics:
        return PlainTextResponse(
            content="# Metrics disabled\n",
            status_code=200,
            media_type=prom_metrics.get_content_type() if prom_metrics else "text/plain"
        )
    
    try:
        return PlainTextResponse(
            content=prom_metrics.get_metrics(),
            status_code=200,
            media_type=prom_metrics.get_content_type()
        )
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        return PlainTextResponse(
            content=f"# Error generating metrics: {str(e)}\n",
            status_code=500,
            media_type="text/plain"
        )
