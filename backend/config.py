import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, ValidationError
from pathlib import Path
from typing import Optional, List, Any
import sys

# Get the directory where this config file is located
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    
    All sensitive configuration must be provided via environment variables.
    The .env file is loaded automatically for development convenience.
    """
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), 
        env_file_encoding='utf-8',
        # Don't ignore extra fields - helps catch typos in .env
        extra='forbid'
    )
    
    # Application Settings
    app_name: str = "SequelSpeak Backend"
    environment: str 
    
    # Security Settings
    secret_key: Optional[str] = None  # Required in production for session/JWT
    allowed_origins: str  # Comma-separated CORS origins
    
    # Database Settings
    db_connection_timeout: int = 10  # Database connection timeout in seconds
    
    # Connection Pool Settings
    db_pool_min_size: int = 1  # Minimum number of connections in pool
    db_pool_max_size: int = 5  # Maximum number of connections in pool
    db_pool_timeout: int = 30  # Pool connection timeout in seconds
    db_pool_max_idle: Optional[int] = None  # Maximum idle time for connections (seconds)
    
    # Health Check Settings
    health_check_timeout: int = 2  # Health check timeout in seconds (keep low for fast response)
    health_check_db_url: Optional[str] = None  # Default database URL for health checks
    
    # Retry Settings
    connection_retry_max: int = 2  # Maximum retries for user connection tests
    connection_retry_initial_delay: float = 1.0  # Initial retry delay in seconds (exponential backoff)
    health_check_retry_max: int = 1  # Maximum retries for health checks (keep low for fast response)
    
    # Rate Limiting Settings
    rate_limit_enabled: bool = True  # Enable rate limiting for API endpoints
    rate_limit_per_minute: int = 10  # Maximum requests per minute per IP for test-connection endpoint
    rate_limit_burst: int = 3  # Allow short bursts of this many requests
    
    # Circuit Breaker Settings
    circuit_breaker_enabled: bool = True  # Enable circuit breaker for database connections
    circuit_breaker_failure_threshold: int = 5  # Number of consecutive failures before opening circuit
    circuit_breaker_timeout: int = 60  # Seconds to wait before trying again after circuit opens
    
    # Authentication Settings (Clerk)
    clerk_secret_key: Optional[str] = None  # Required for JWT verification
    clerk_publishable_key: Optional[str] = None  # Optional, for reference/debugging
    
    # Metrics Settings
    metrics_enabled: bool = True  # Enable Prometheus metrics collection
    app_version: str = "1.0.0"  # Application version for metrics labeling
    
    # Redis Settings (Conversation State Storage)
    redis_enabled: bool = True  # Enable Redis-backed conversation state
    redis_host: str = "localhost"  # Redis server host
    redis_port: int = 6379  # Redis server port
    redis_db: int = 0  # Redis database number (0-15)
    redis_password: Optional[str] = None  # Redis authentication password
    redis_ssl: bool = False  # Enable SSL/TLS for Redis connection
    redis_timeout: int = 5  # Redis connection timeout in seconds
    conversation_state_ttl: int = 86400  # Conversation state TTL in seconds (24 hours)

    model_config = SettingsConfigDict(
        env_file=".env" if os.getenv("ENVIRONMENT") != "production" else None,
        env_file_encoding='utf-8',
        extra='forbid'
    )
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of the allowed values."""
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got: {v}")
        return v
    
    @field_validator('allowed_origins')
    @classmethod
    def validate_cors_origins(cls, v: str, info: Any) -> str:
        """Validate CORS configuration based on environment."""
        environment = info.data.get('environment', 'development') if hasattr(info, 'data') and info.data else 'development'
        
        if environment == "production" and v == "*":
            raise ValueError(
                "Wildcard CORS origins (*) are not allowed in production. "
                "Please specify explicit origins."
            )
        
        # Validate individual origins if not wildcard
        if v != "*":
            origins = [o.strip() for o in v.split(',') if o.strip()]
            for origin in origins:
                if not origin.startswith(('http://', 'https://')):
                    raise ValueError(
                        f"Invalid origin '{origin}'. Must start with http:// or https://"
                    )
        
        return v
    
    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: Optional[str], info: Any) -> Optional[str]:
        """Ensure secret_key is set in production."""
        # Convert empty string to None for consistency
        if v == '':
            v = None
        
        # Access environment from ValidationInfo context
        environment = info.data.get('environment', 'development') if hasattr(info, 'data') and info.data else 'development'
        
        if environment == 'production' and not v:
            raise ValueError(
                "secret_key is required in production environment. "
                "Set SECRET_KEY environment variable."
            )
        
        # Warn if using default/weak secret in non-dev
        if v and len(v) < 32 and environment != 'development':
            print(
                f"WARNING: secret_key should be at least 32 characters long. "
                f"Current length: {len(v)}",
                file=sys.stderr
            )
        
        return v
    
    @field_validator('db_connection_timeout')
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Ensure timeout is positive."""
        if v <= 0:
            raise ValueError(f"db_connection_timeout must be positive, got: {v}")
        if v > 300:
            print(
                f"WARNING: db_connection_timeout is very high ({v}s). "
                f"Consider reducing to avoid long hangs.",
                file=sys.stderr
            )
        return v
    
    @field_validator('db_pool_min_size')
    @classmethod
    def validate_pool_min_size(cls, v: int) -> int:
        """Ensure pool min size is positive."""
        if v < 0:
            raise ValueError(f"db_pool_min_size must be non-negative, got: {v}")
        return v
    
    @field_validator('db_pool_max_size')
    @classmethod
    def validate_pool_max_size(cls, v: int) -> int:
        """Ensure pool max size is positive and reasonable."""
        if v <= 0:
            raise ValueError(f"db_pool_max_size must be positive, got: {v}")
        if v > 50:
            print(
                f"WARNING: db_pool_max_size is very high ({v}). "
                f"This may exhaust PostgreSQL max_connections. Consider reducing.",
                file=sys.stderr
            )
        return v
    
    @field_validator('db_pool_timeout')
    @classmethod
    def validate_pool_timeout(cls, v: int) -> int:
        """Ensure pool timeout is positive."""
        if v <= 0:
            raise ValueError(f"db_pool_timeout must be positive, got: {v}")
        return v
    
    @field_validator('health_check_timeout')
    @classmethod
    def validate_health_check_timeout(cls, v: int) -> int:
        """Ensure health check timeout is positive and reasonably low for fast response."""
        if v <= 0:
            raise ValueError(f"health_check_timeout must be positive, got: {v}")
        if v > 10:
            print(
                f"WARNING: health_check_timeout is high ({v}s). "
                f"Consider keeping under 10s for fast /health responses.",
                file=sys.stderr
            )
            # Cap at 10 seconds to prevent long hangs
            return 10
        return v
    
    @field_validator('connection_retry_max')
    @classmethod
    def validate_connection_retry_max(cls, v: int) -> int:
        """Ensure connection retry max is non-negative and reasonable."""
        if v < 0:
            raise ValueError(f"connection_retry_max must be non-negative, got: {v}")
        if v > 5:
            print(
                f"WARNING: connection_retry_max is very high ({v}). "
                f"Consider keeping under 5 to avoid long wait times.",
                file=sys.stderr
            )
        return v
    
    @field_validator('health_check_retry_max')
    @classmethod
    def validate_health_check_retry_max(cls, v: int) -> int:
        """Ensure health check retry max is non-negative and low for fast response."""
        if v < 0:
            raise ValueError(f"health_check_retry_max must be non-negative, got: {v}")
        if v > 2:
            print(
                f"WARNING: health_check_retry_max is high ({v}). "
                f"Consider keeping at 1-2 for fast health check responses.",
                file=sys.stderr
            )
        return v
    
    @field_validator('connection_retry_initial_delay')
    @classmethod
    def validate_connection_retry_initial_delay(cls, v: float) -> float:
        """Ensure initial retry delay is positive."""
        if v <= 0:
            raise ValueError(f"connection_retry_initial_delay must be positive, got: {v}")
        if v > 5.0:
            print(
                f"WARNING: connection_retry_initial_delay is very high ({v}s). "
                f"Consider keeping under 5s for responsive retries.",
                file=sys.stderr
            )
        return v
    
    @field_validator('redis_port')
    @classmethod
    def validate_redis_port(cls, v: int) -> int:
        """Ensure Redis port is valid."""
        if v <= 0 or v > 65535:
            raise ValueError(f"redis_port must be between 1 and 65535, got: {v}")
        return v
    
    @field_validator('redis_db')
    @classmethod
    def validate_redis_db(cls, v: int) -> int:
        """Ensure Redis database number is valid (0-15)."""
        if v < 0 or v > 15:
            raise ValueError(f"redis_db must be between 0 and 15, got: {v}")
        return v
    
    @field_validator('redis_timeout')
    @classmethod
    def validate_redis_timeout(cls, v: int) -> int:
        """Ensure Redis timeout is positive."""
        if v <= 0:
            raise ValueError(f"redis_timeout must be positive, got: {v}")
        if v > 30:
            print(
                f"WARNING: redis_timeout is very high ({v}s). "
                f"Consider keeping under 30s for responsive connections.",
                file=sys.stderr
            )
        return v
    
    @field_validator('conversation_state_ttl')
    @classmethod
    def validate_conversation_state_ttl(cls, v: int) -> int:
        """Validate conversation state TTL."""
        if v < 0:
            raise ValueError(f"conversation_state_ttl must be non-negative, got: {v}")
        if v == 0:
            print(
                "WARNING: conversation_state_ttl is 0 (no expiration). "
                "This may lead to unbounded Redis memory growth.",
                file=sys.stderr
            )
        if v > 2592000:  # 30 days
            print(
                f"WARNING: conversation_state_ttl is very high ({v}s = {v//86400} days). "
                f"Consider keeping under 30 days to prevent memory bloat.",
                file=sys.stderr
            )
        return v
    
    def get_allowed_origins_list(self) -> List[str]:
        """Parse allowed_origins string into list."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(',') if origin.strip()]
    
    def validate_no_secrets_hardcoded(self) -> None:
        """
        Verify no sensitive data is hard-coded in defaults.
        This is a runtime check to ensure config module doesn't contain secrets.
        """
        # Check that secret_key wasn't set via default (should only come from env)
        # In Pydantic v2, we access defaults via model_fields on the class
        field = self.__class__.model_fields.get('secret_key')
        if field and isinstance(field.default, str) and field.default:
            raise ValueError(
                "secret_key appears to be hard-coded. "
                "It must only be loaded from environment variables."
            )


def load_settings() -> Settings:
    """
    Load and validate settings.
    
    Returns validated Settings object or raises ValidationError with clear message.
    """
    try:
        settings = Settings()  # type: ignore[call-arg]
        settings.validate_no_secrets_hardcoded()
        return settings
    except ValidationError as e:
        print("\n❌ Configuration Error:", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for error in e.errors():
            field = " -> ".join(str(x) for x in error['loc'])
            msg = error['msg']
            print(f"  {field}: {msg}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("\nPlease check your environment variables and .env file.", file=sys.stderr)
        print("See .env.example for required configuration.\n", file=sys.stderr)
        raise


# Singleton instance - load on module import
# This will fail fast if configuration is invalid
settings = load_settings()
