import pytest
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from config import Settings

def test_config_defaults():
    """Test that default values are set correctly."""
    # Ensure no env vars interfere
    with pytest.MonkeyPatch.context() as m:
        m.delenv("SECRET_KEY", raising=False)
        m.delenv("ENVIRONMENT", raising=False)
        
        settings = Settings()
        assert settings.app_name == "SequelSpeak Backend"
        assert settings.environment == "development"
        assert settings.db_connection_timeout == 10
        assert settings.allowed_origins == "*"
        assert settings.secret_key is None

def test_environment_validation():
    """Test environment variable validation."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "invalid_env")
        with pytest.raises(ValidationError) as exc:
            Settings()
        assert "environment must be one of" in str(exc.value)

def test_production_secret_key_required():
    """Test that secret_key is required in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.delenv("SECRET_KEY", raising=False)
        
        with pytest.raises(ValidationError) as exc:
            Settings()
        assert "secret_key is required in production" in str(exc.value)

def test_production_secret_key_valid():
    """Test that valid secret key works in production."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "super_secret_key_that_is_long_enough_32chars")
        
        settings = Settings()
        assert settings.environment == "production"
        assert settings.secret_key == "super_secret_key_that_is_long_enough_32chars"

def test_timeout_validation():
    """Test database timeout validation."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("DB_CONNECTION_TIMEOUT", "-5")
        with pytest.raises(ValidationError):
            Settings()

def test_allowed_origins_parsing():
    """Test parsing of allowed origins list."""
    # Test wildcard
    s1 = Settings(allowed_origins="*")
    assert s1.get_allowed_origins_list() == ["*"]
    
    # Test list
    s2 = Settings(allowed_origins="http://localhost:3000, https://app.example.com")
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
