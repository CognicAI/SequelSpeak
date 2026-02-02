from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator, ValidationError
from pathlib import Path
from typing import Optional, List
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
    model_config = ConfigDict(
        env_file=str(ENV_FILE), 
        env_file_encoding='utf-8',
        # Don't ignore extra fields - helps catch typos in .env
        extra='forbid'
    )
    
    # Application Settings
    app_name: str = "SequelSpeak Backend"
    environment: str = "development"
    
    # Security Settings
    secret_key: Optional[str] = None  # Required in production for session/JWT
    allowed_origins: str = "*"  # Comma-separated CORS origins
    
    # Database Settings
    db_connection_timeout: int = 10  # Database connection timeout in seconds
    
    # Health Check Settings
    health_check_timeout: int = 2  # Health check timeout in seconds (keep low for fast response)
    health_check_db_url: Optional[str] = None  # Default database URL for health checks
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of the allowed values."""
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got: {v}")
        return v
    
    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure secret_key is set in production."""
        # Access environment from ValidationInfo context
        environment = info.data.get('environment', 'development')
        
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
        settings = Settings()
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
