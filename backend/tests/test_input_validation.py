"""
Security Input Validation Tests

Tests for the input validation module that checks database connection URLs
for injection patterns and dangerous characters.
"""

import sys
import os
import pytest

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.input_validator import (
    validate_connection_url,
    contains_null_bytes,
    contains_sql_injection_patterns,
    contains_command_injection_patterns,
    contains_control_characters,
    validate_url_length,
    sanitize_for_logging,
    MAX_URL_LENGTH,
)


# ============================================================================
# NULL BYTE DETECTION TESTS
# ============================================================================

class TestNullByteDetection:
    """Tests for null byte detection."""
    
    def test_detects_raw_null_byte(self):
        """Detect raw null byte character."""
        assert contains_null_bytes("postgres://user\x00:pass@host/db") is True
    
    def test_detects_url_encoded_null_byte(self):
        """Detect URL-encoded null byte (%00)."""
        assert contains_null_bytes("postgres://user%00:pass@host/db") is True
    
    def test_detects_uppercase_url_encoded_null(self):
        """Detect uppercase URL-encoded null byte."""
        assert contains_null_bytes("postgres://user%00pass@host/db") is True
    
    def test_no_false_positive_on_valid_url(self):
        """Valid URLs should not trigger null byte detection."""
        assert contains_null_bytes("postgres://user:pass@host:5432/db") is False
    
    def test_empty_string(self):
        """Empty string should return False."""
        assert contains_null_bytes("") is False
    
    def test_none_input(self):
        """None should return False."""
        assert contains_null_bytes(None) is False


# ============================================================================
# SQL INJECTION PATTERN TESTS
# ============================================================================

class TestSQLInjectionPatterns:
    """Tests for SQL injection pattern detection."""
    
    def test_detects_line_comment(self):
        """Detect SQL line comment."""
        assert contains_sql_injection_patterns("postgres://user--:pass@host/db") is True
    
    def test_detects_block_comment_start(self):
        """Detect SQL block comment start."""
        assert contains_sql_injection_patterns("postgres://user/*:pass@host/db") is True
    
    def test_detects_block_comment_end(self):
        """Detect SQL block comment end."""
        assert contains_sql_injection_patterns("postgres://user*/:pass@host/db") is True
    
    def test_detects_union_select(self):
        """Detect UNION SELECT pattern."""
        assert contains_sql_injection_patterns("postgres://user:pass@host/db?name=union select") is True
    
    def test_detects_or_1_equals_1(self):
        """Detect OR 1=1 pattern."""
        assert contains_sql_injection_patterns("postgres://user:pass@host/db?id=1 or 1=1") is True
    
    def test_detects_drop_table(self):
        """Detect DROP TABLE pattern."""
        assert contains_sql_injection_patterns("postgres://user:pass@host/db;drop table users") is True
    
    def test_no_false_positive_valid_url(self):
        """Valid URLs should not trigger SQL injection detection."""
        assert contains_sql_injection_patterns("postgres://user:pass@host:5432/db") is False
    
    def test_no_false_positive_on_common_words(self):
        """Common words like 'updated' should not trigger false positives."""
        # 'update ' with space is checked, 'updated' should be fine
        assert contains_sql_injection_patterns("postgres://user:pass@host/updated_db") is False


# ============================================================================
# COMMAND INJECTION PATTERN TESTS
# ============================================================================

class TestCommandInjectionPatterns:
    """Tests for command injection pattern detection."""
    
    def test_detects_command_substitution_dollar(self):
        """Detect $() command substitution."""
        assert contains_command_injection_patterns("postgres://user:$(whoami)@host/db") is True
    
    def test_detects_command_substitution_backtick(self):
        """Detect backtick command substitution."""
        assert contains_command_injection_patterns("postgres://user:`whoami`@host/db") is True
    
    def test_detects_pipe_with_command(self):
        """Detect pipe character followed by shell command."""
        assert contains_command_injection_patterns("postgres://user:pass|cat /etc/passwd@host/db") is True
    
    def test_allows_pipe_in_password(self):
        """Allow pipe character in password when not followed by command."""
        # Pipe in password without command-like content after it
        assert contains_command_injection_patterns("postgres://user:pass|word@host/db") is False
    
    def test_allows_url_encoded_pipe(self):
        """URL-encoded pipe (%7C) should be allowed."""
        assert contains_command_injection_patterns("postgres://user:pass%7Cword@host/db") is False
    
    def test_detects_and_operator(self):
        """Detect && operator."""
        assert contains_command_injection_patterns("postgres://user:pass&&rm -rf@host/db") is True
    
    def test_detects_or_operator(self):
        """Detect || operator."""
        assert contains_command_injection_patterns("postgres://user:pass||echo@host/db") is True
    
    def test_detects_newline_injection(self):
        """Detect newline character (potential command injection)."""
        assert contains_command_injection_patterns("postgres://user:pass\nrm -rf@host/db") is True
    
    def test_no_false_positive_valid_url(self):
        """Valid URLs should not trigger command injection detection."""
        assert contains_command_injection_patterns("postgres://user:pass@host:5432/db") is False
    
    def test_allows_url_encoded_special_chars(self):
        """URL-encoded special characters in passwords should be allowed."""
        # %24 is $, which is fine when URL-encoded
        assert contains_command_injection_patterns("postgres://user:p%24ss@host/db") is False
    
    def test_allows_semicolon_in_query_params(self):
        """Semicolons in query parameters should be allowed (valid URL syntax)."""
        # This is explicitly mentioned as a valid use case in input_validator.py
        assert contains_command_injection_patterns("postgres://user:pass@host/db?sslmode=require;connect_timeout=10") is False


# ============================================================================
# CONTROL CHARACTER TESTS
# ============================================================================

class TestControlCharacterDetection:
    """Tests for control character detection."""
    
    def test_detects_bell_character(self):
        """Detect bell character (ASCII 7)."""
        assert contains_control_characters("postgres://user\x07:pass@host/db") is True
    
    def test_detects_backspace(self):
        """Detect backspace character (ASCII 8)."""
        assert contains_control_characters("postgres://user\x08:pass@host/db") is True
    
    def test_detects_escape(self):
        """Detect escape character (ASCII 27)."""
        assert contains_control_characters("postgres://user\x1b:pass@host/db") is True
    
    def test_detects_del_character(self):
        """Detect DEL character (ASCII 127)."""
        assert contains_control_characters("postgres://user\x7f:pass@host/db") is True
    
    def test_allows_tab_character(self):
        """Tab character should be allowed."""
        assert contains_control_characters("postgres://user\t:pass@host/db") is False
    
    def test_no_false_positive_valid_url(self):
        """Valid URLs should not trigger control character detection."""
        assert contains_control_characters("postgres://user:pass@host:5432/db") is False


# ============================================================================
# URL LENGTH VALIDATION TESTS
# ============================================================================

class TestURLLengthValidation:
    """Tests for URL length validation."""
    
    def test_accepts_normal_url(self):
        """Normal length URLs should be accepted."""
        assert validate_url_length("postgres://user:pass@host:5432/db") is True
    
    def test_accepts_max_length_url(self):
        """URL at exactly max length should be accepted."""
        base_url = "postgres://user:pass@host:5432/"
        padding = "a" * (MAX_URL_LENGTH - len(base_url))
        assert validate_url_length(base_url + padding) is True
    
    def test_rejects_too_long_url(self):
        """URL exceeding max length should be rejected."""
        very_long_url = "postgres://user:pass@host:5432/" + "a" * (MAX_URL_LENGTH + 1)
        assert validate_url_length(very_long_url) is False
    
    def test_accepts_empty_url(self):
        """Empty URL passes length check (caught elsewhere)."""
        assert validate_url_length("") is True


# ============================================================================
# COMPREHENSIVE VALIDATION TESTS
# ============================================================================

class TestValidateConnectionURL:
    """Tests for the main validate_connection_url function."""
    
    def test_valid_postgres_url(self):
        """Valid postgres:// URL should pass."""
        result = validate_connection_url("postgres://user:pass@localhost:5432/db")
        assert result.is_valid is True
        assert result.error_message is None
    
    def test_valid_postgresql_url(self):
        """Valid postgresql:// URL should pass."""
        result = validate_connection_url("postgresql://user:pass@localhost:5432/db")
        assert result.is_valid is True
    
    def test_valid_url_with_special_chars_encoded(self):
        """URL with properly encoded special characters should pass."""
        result = validate_connection_url("postgres://user:p%40ss%23word@localhost:5432/db")
        assert result.is_valid is True
    
    def test_valid_url_with_query_params(self):
        """URL with query parameters should pass."""
        result = validate_connection_url("postgres://user:pass@localhost:5432/db?sslmode=require")
        assert result.is_valid is True
    
    def test_rejects_none(self):
        """None should be rejected."""
        result = validate_connection_url(None)
        assert result.is_valid is False
        assert result.error_type == "empty_input"
    
    def test_rejects_empty_string(self):
        """Empty string should be rejected."""
        result = validate_connection_url("")
        assert result.is_valid is False
        assert result.error_type == "empty_input"
    
    def test_rejects_whitespace_only(self):
        """Whitespace-only string should be rejected."""
        result = validate_connection_url("   ")
        assert result.is_valid is False
        assert result.error_type == "empty_input"
    
    def test_rejects_null_byte(self):
        """URL with null byte should be rejected."""
        result = validate_connection_url("postgres://user\x00:pass@host/db")
        assert result.is_valid is False
        assert result.error_type == "null_byte"
    
    def test_rejects_sql_injection(self):
        """URL with SQL injection pattern should be rejected."""
        result = validate_connection_url("postgres://user--:pass@host/db")
        assert result.is_valid is False
        assert result.error_type == "sql_injection"
    
    def test_rejects_command_injection(self):
        """URL with command injection pattern should be rejected."""
        result = validate_connection_url("postgres://user:$(cmd)@host/db")
        assert result.is_valid is False
        assert result.error_type == "command_injection"
    
    def test_rejects_control_characters(self):
        """URL with control characters should be rejected."""
        result = validate_connection_url("postgres://user\x07:pass@host/db")
        assert result.is_valid is False
        assert result.error_type == "control_char"
    
    def test_rejects_too_long_url(self):
        """Excessively long URL should be rejected."""
        very_long_url = "postgres://user:pass@host/" + "a" * 3000
        result = validate_connection_url(very_long_url)
        assert result.is_valid is False
        assert result.error_type == "length_exceeded"
    
    def test_error_messages_are_user_friendly(self):
        """Error messages should not expose internal details."""
        result = validate_connection_url("postgres://user\x00:pass@host/db")
        assert "null" not in result.error_message.lower()
        assert "invalid" in result.error_message.lower()


# ============================================================================
# SANITIZE FOR LOGGING TESTS
# ============================================================================

class TestSanitizeForLogging:
    """Tests for the sanitize_for_logging function."""
    
    def test_sanitizes_null_byte(self):
        """Null byte should be replaced with <NUL>."""
        result = sanitize_for_logging("test\x00value")
        assert result == "test<NUL>value"
    
    def test_sanitizes_control_characters(self):
        """Control characters should be replaced with hex codes."""
        result = sanitize_for_logging("test\x07value")
        assert result == "test<07>value"
    
    def test_sanitizes_del_character(self):
        """DEL character should be replaced."""
        result = sanitize_for_logging("test\x7fvalue")
        assert result == "test<DEL>value"
    
    def test_preserves_normal_text(self):
        """Normal text should be preserved."""
        result = sanitize_for_logging("normal text 123")
        assert result == "normal text 123"
    
    def test_handles_none(self):
        """None should return empty string."""
        assert sanitize_for_logging(None) == ""
    
    def test_handles_empty_string(self):
        """Empty string should return empty string."""
        assert sanitize_for_logging("") == ""


# ============================================================================
# INTEGRATION WITH CONNECTION SERVICE TESTS
# ============================================================================

class TestIntegrationWithConnectionService:
    """Integration tests verifying validation works with DBConnectionService."""
    
    def test_connection_service_rejects_null_byte(self):
        """DBConnectionService should reject URLs with null bytes."""
        from services.db_connection_service import DBConnectionService
        from schemas.errors import ErrorCode
        
        result = DBConnectionService.parse_and_verify_url("postgres://user\x00:pass@host/db")
        assert result.success is False
        assert result.error_code == ErrorCode.INVALID_URL
    
    def test_connection_service_rejects_sql_injection(self):
        """DBConnectionService should reject URLs with SQL injection patterns."""
        from services.db_connection_service import DBConnectionService
        from schemas.errors import ErrorCode
        
        result = DBConnectionService.parse_and_verify_url("postgres://user--:pass@host/db")
        assert result.success is False
        assert result.error_code == ErrorCode.INVALID_URL
    
    def test_connection_service_accepts_valid_url(self):
        """DBConnectionService should accept valid URLs."""
        from services.db_connection_service import DBConnectionService
        
        result = DBConnectionService.parse_and_verify_url("postgres://user:pass@localhost:5432/db")
        assert result.success is True
    
    def test_connection_service_accepts_complex_password(self):
        """DBConnectionService should accept valid URLs with encoded special chars."""
        from services.db_connection_service import DBConnectionService
        
        # Password with encoded special chars: p@ss#word!
        result = DBConnectionService.parse_and_verify_url("postgres://user:p%40ss%23word%21@localhost:5432/db")
        assert result.success is True
