import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path

from pydantic import ValidationError
from config import Settings

def test_config_defaults():
    """Test that default values are set correctly."""
    # Ensure no env vars interfere and prevent loading .env file
    with pytest.MonkeyPatch.context() as m:
        m.delenv("SECRET_KEY", raising=False)
        m.delenv("APP_NAME", raising=False)
        m.delenv("HEALTH_CHECK_DB_URL", raising=False)
        
        # environment and allowed_origins are now required fields
        m.setenv("ENVIRONMENT", "development")
        m.setenv("ALLOWED_ORIGINS", "*")
        
        # Use _env_file=None to prevent loading the default .env file
        settings = Settings(_env_file=None)
        assert settings.app_name == "SequelSpeak Backend"
        assert settings.environment == "development"
        assert settings.db_connection_timeout == 10
        assert settings.allowed_origins == "*"
        assert settings.secret_key is None

def test_environment_validation():
    """Test environment variable validation."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "invalid_env")
        m.setenv("ALLOWED_ORIGINS", "*")  # Required field
        with pytest.raises(ValidationError) as exc:
            Settings()
        assert "environment must be one of" in str(exc.value)

def test_production_secret_key_required():
    """Test that secret_key is required in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.setenv("ALLOWED_ORIGINS", "https://app.example.com")  # Required field, and wildcard not allowed in production
        m.delenv("SECRET_KEY", raising=False)
        m.delenv("APP_NAME", raising=False)
        m.delenv("HEALTH_CHECK_DB_URL", raising=False)
        
        # Use _env_file=None to prevent loading the default .env file
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "secret_key is required in production" in str(exc.value)

def test_production_secret_key_valid():
    """Test that valid secret key works in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "super_secret_key_that_is_long_enough_32chars")
        m.setenv("ALLOWED_ORIGINS", "https://app.example.com")  # Production requires explicit origins
        
        settings = Settings()
        assert settings.environment == "production"
        assert settings.secret_key == "super_secret_key_that_is_long_enough_32chars"

def test_timeout_validation():
    """Test database timeout validation."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "development")  # Required field
        m.setenv("ALLOWED_ORIGINS", "*")  # Required field
        m.setenv("DB_CONNECTION_TIMEOUT", "-5")
        with pytest.raises(ValidationError):
            Settings()

def test_allowed_origins_parsing():
    """Test parsing of allowed origins list."""
    # Test wildcard (only allowed in non-production)
    s1 = Settings(environment="development", allowed_origins="*")
    assert s1.get_allowed_origins_list() == ["*"]
    
    # Test list
    s2 = Settings(environment="development", allowed_origins="http://localhost:3000, https://app.example.com")
    origins = s2.get_allowed_origins_list()
    assert len(origins) == 2
    assert "http://localhost:3000" in origins
    assert "https://app.example.com" in origins

def test_no_hardcoded_secrets_check():
    """Test that hardcoded secrets are detected."""
    from pydantic_settings import BaseSettings
    
    # Simulate a class with a hardcoded secret default
    class MockBadSettings(BaseSettings):
        secret_key: str = "hardcoded_secret"
    
    # Should fail validation when calling the method from Settings
    with pytest.raises(ValueError, match="hard-coded"):
        # We manually call the validation method from Settings class on this mock instance
        Settings.validate_no_secrets_hardcoded(MockBadSettings())
def test_cors_wildcard_blocked_in_production():
    """Test that wildcard CORS origins are blocked in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.setenv("ALLOWED_ORIGINS", "*")
        m.setenv("SECRET_KEY", "super_secret_key_that_is_long_enough_32chars")
        
        with pytest.raises(ValidationError) as exc:
            Settings()
        assert "Wildcard CORS origins (*) are not allowed in production" in str(exc.value)

def test_cors_explicit_origins_in_production():
    """Test that explicit CORS origins work in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.setenv("ALLOWED_ORIGINS", "https://app.example.com,https://api.example.com")
        m.setenv("SECRET_KEY", "super_secret_key_that_is_long_enough_32chars")
        
        settings = Settings()
        origins = settings.get_allowed_origins_list()
        assert len(origins) == 2
        assert "https://app.example.com" in origins
        assert "https://api.example.com" in origins

def test_cors_invalid_origin_format():
    """Test that invalid origin formats are rejected."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "development")
        m.setenv("ALLOWED_ORIGINS", "invalid-origin-without-protocol")
        
        with pytest.raises(ValidationError) as exc:
            Settings()
        assert "Must start with http:// or https://" in str(exc.value)

def test_cors_wildcard_allowed_in_development():
    """Test that wildcard CORS origins are allowed in development."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "development")
        m.setenv("ALLOWED_ORIGINS", "*")
        
        settings = Settings()
        assert settings.allowed_origins == "*"
        assert settings.get_allowed_origins_list() == ["*"]
