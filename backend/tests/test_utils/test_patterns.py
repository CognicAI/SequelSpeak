"""
Tests for centralized pattern matching utilities.

Tests cover:
- Pattern matching for all categories
- Regex pattern support
- Case-sensitive and case-insensitive matching
- Pattern discovery
- Runtime pattern addition
"""

import sys
import os
import pytest

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from utils.patterns import PatternMatcher, PatternCategory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestPatternMatcher:
    """Tests for the centralized PatternMatcher class."""
    
    def test_sql_injection_patterns(self):
        """Test SQL injection pattern detection."""
        # Should detect SQL injection patterns
        assert PatternMatcher.matches("DROP TABLE users", PatternCategory.SQL_INJECTION)
        assert PatternMatcher.matches("UNION SELECT * FROM passwords", PatternCategory.SQL_INJECTION)
        assert PatternMatcher.matches("OR 1=1", PatternCategory.SQL_INJECTION)
        assert PatternMatcher.matches("'; DROP TABLE--", PatternCategory.SQL_INJECTION)
        
        # Should not match legitimate content
        assert not PatternMatcher.matches("my-database", PatternCategory.SQL_INJECTION)
        assert not PatternMatcher.matches("normal_user", PatternCategory.SQL_INJECTION)
    
    def test_command_injection_patterns(self):
        """Test command injection pattern detection."""
        # Should detect command injection patterns
        assert PatternMatcher.matches("$(rm -rf /)", PatternCategory.COMMAND_INJECTION)
        assert PatternMatcher.matches("`cat /etc/passwd`", PatternCategory.COMMAND_INJECTION)
        assert PatternMatcher.matches("test && malicious", PatternCategory.COMMAND_INJECTION)
        assert PatternMatcher.matches("a || b", PatternCategory.COMMAND_INJECTION)
        
        # Should not match legitimate content
        assert not PatternMatcher.matches("normal_password", PatternCategory.COMMAND_INJECTION)
    
    def test_connection_lost_patterns(self):
        """Test connection lost pattern detection."""
        # Should detect connection lost patterns
        assert PatternMatcher.matches("connection closed", PatternCategory.CONNECTION_LOST)
        assert PatternMatcher.matches("server closed the connection unexpectedly", PatternCategory.CONNECTION_LOST)
        assert PatternMatcher.matches("connection reset by peer", PatternCategory.CONNECTION_LOST)
        assert PatternMatcher.matches("broken pipe error", PatternCategory.CONNECTION_LOST)
        
        # Should not match other errors
        assert not PatternMatcher.matches("authentication failed", PatternCategory.CONNECTION_LOST)
    
    def test_ssl_error_patterns(self):
        """Test SSL/TLS error pattern detection."""
        # Should detect SSL errors
        assert PatternMatcher.matches("ssl error: certificate verify failed", PatternCategory.SSL_ERROR)
        assert PatternMatcher.matches("certificate_verify_failed", PatternCategory.SSL_ERROR)
        assert PatternMatcher.matches("self-signed certificate", PatternCategory.SSL_ERROR)
        assert PatternMatcher.matches("certificate expired", PatternCategory.SSL_ERROR)
        
        # Should not match non-SSL errors
        assert not PatternMatcher.matches("connection timeout", PatternCategory.SSL_ERROR)
    
    def test_auth_error_patterns(self):
        """Test authentication error pattern detection."""
        # Should detect auth errors
        assert PatternMatcher.matches("password authentication failed", PatternCategory.AUTH_ERROR)
        assert PatternMatcher.matches("authentication failed for user", PatternCategory.AUTH_ERROR)
        assert PatternMatcher.matches("no pg_hba.conf entry", PatternCategory.AUTH_ERROR)
        assert PatternMatcher.matches("permission denied", PatternCategory.AUTH_ERROR)
        
        # Should not match other errors
        assert not PatternMatcher.matches("database does not exist", PatternCategory.AUTH_ERROR)
    
    def test_database_not_found_patterns(self):
        """Test database not found pattern detection with regex."""
        # Should detect database not found errors (regex patterns)
        assert PatternMatcher.matches('database "test" does not exist', PatternCategory.DATABASE_NOT_FOUND)
        assert PatternMatcher.matches('FATAL: database "mydb" does not exist', PatternCategory.DATABASE_NOT_FOUND)
        assert PatternMatcher.matches('does not exist: database connection', PatternCategory.DATABASE_NOT_FOUND)
        
        # Should not match other errors
        assert not PatternMatcher.matches("table does not exist", PatternCategory.DATABASE_NOT_FOUND)
    
    def test_timeout_error_patterns(self):
        """Test timeout error pattern detection."""
        # Should detect timeout errors
        assert PatternMatcher.matches("timeout expired", PatternCategory.TIMEOUT_ERROR)
        assert PatternMatcher.matches("connection timed out", PatternCategory.TIMEOUT_ERROR)
        assert PatternMatcher.matches("operation timed out after 10s", PatternCategory.TIMEOUT_ERROR)
        
        # Should not match other errors
        assert not PatternMatcher.matches("connection reset", PatternCategory.TIMEOUT_ERROR)
    
    def test_host_unreachable_patterns(self):
        """Test host unreachable pattern detection."""
        # Should detect host unreachable errors
        assert PatternMatcher.matches("could not connect to server", PatternCategory.HOST_UNREACHABLE)
        assert PatternMatcher.matches("connection refused", PatternCategory.HOST_UNREACHABLE)
        assert PatternMatcher.matches("network is unreachable", PatternCategory.HOST_UNREACHABLE)
        assert PatternMatcher.matches("ssl syscall error", PatternCategory.HOST_UNREACHABLE)
        
        # Should not match other errors
        assert not PatternMatcher.matches("authentication failed", PatternCategory.HOST_UNREACHABLE)
    
    def test_case_sensitivity(self):
        """Test case-sensitive and case-insensitive matching."""
        # Default is case-insensitive
        assert PatternMatcher.matches("DROP TABLE", PatternCategory.SQL_INJECTION)
        assert PatternMatcher.matches("drop table", PatternCategory.SQL_INJECTION)
        assert PatternMatcher.matches("DrOp TaBlE", PatternCategory.SQL_INJECTION)
        
        # Case-sensitive mode
        assert PatternMatcher.matches("drop table", PatternCategory.SQL_INJECTION, case_sensitive=True)
        # Note: patterns are lowercase, so uppercase won't match in case-sensitive mode
        assert not PatternMatcher.matches("DROP TABLE", PatternCategory.SQL_INJECTION, case_sensitive=True)
    
    def test_find_matches(self):
        """Test finding all matching patterns."""
        # Single match
        matches = PatternMatcher.find_matches("connection closed", PatternCategory.CONNECTION_LOST)
        assert "connection closed" in matches
        
        # Multiple matches
        text = "ssl error: certificate expired"
        matches = PatternMatcher.find_matches(text, PatternCategory.SSL_ERROR)
        assert len(matches) >= 2  # Should match both "ssl error" and "certificate expired"
        assert "ssl error" in matches
        assert "certificate expired" in matches
        
        # No matches
        matches = PatternMatcher.find_matches("normal text", PatternCategory.SQL_INJECTION)
        assert len(matches) == 0
    
    def test_get_patterns(self):
        """Test retrieving all patterns for a category."""
        # Get SQL injection patterns
        patterns = PatternMatcher.get_patterns(PatternCategory.SQL_INJECTION)
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert "drop table" in patterns
        assert "union select" in patterns
        
        # Get connection lost patterns
        patterns = PatternMatcher.get_patterns(PatternCategory.CONNECTION_LOST)
        assert isinstance(patterns, list)
        assert "connection closed" in patterns
        assert "broken pipe" in patterns
    
    def test_add_pattern(self):
        """Test adding patterns at runtime."""
        # Add a new pattern
        test_category = PatternCategory.SQL_INJECTION
        test_pattern = "custom_test_pattern_xyz"
        
        # Ensure pattern doesn't exist yet
        assert not PatternMatcher.matches(test_pattern, test_category)
        
        # Add the pattern
        PatternMatcher.add_pattern(test_category, test_pattern)
        
        # Now it should match
        assert PatternMatcher.matches(test_pattern, test_category)
        
        # Clean up - remove the test pattern
        PatternMatcher.PATTERNS[test_category].remove(test_pattern)
    
    def test_matches_any_category(self):
        """Test matching against multiple categories."""
        # Should match SQL injection
        categories = [PatternCategory.SQL_INJECTION, PatternCategory.COMMAND_INJECTION]
        assert PatternMatcher.matches_any_category("DROP TABLE users", categories)
        
        # Should match command injection
        assert PatternMatcher.matches_any_category("$(rm -rf /)", categories)
        
        # Should not match either
        assert not PatternMatcher.matches_any_category("normal text", categories)
    
    def test_empty_text(self):
        """Test behavior with empty text."""
        assert not PatternMatcher.matches("", PatternCategory.SQL_INJECTION)
        assert not PatternMatcher.matches(None, PatternCategory.SQL_INJECTION)
        assert PatternMatcher.find_matches("", PatternCategory.SQL_INJECTION) == []
        assert PatternMatcher.find_matches(None, PatternCategory.SQL_INJECTION) == []
    
    def test_regex_patterns(self):
        """Test that regex patterns work correctly."""
        # Database not found uses regex patterns
        assert PatternMatcher.matches(
            'database "test" does not exist',
            PatternCategory.DATABASE_NOT_FOUND
        )
        
        # Test the reverse order pattern
        assert PatternMatcher.matches(
            'does not exist: database "mydb"',
            PatternCategory.DATABASE_NOT_FOUND
        )
    
    def test_pattern_priority(self):
        """Test that patterns are checked in the order they appear."""
        # SSL SYSCALL should match HOST_UNREACHABLE, not SSL_ERROR
        text = "ssl syscall error: connection reset"
        
        # Should match HOST_UNREACHABLE
        assert PatternMatcher.matches(text, PatternCategory.HOST_UNREACHABLE)
        
        # Should also match SSL_ERROR since it contains "ssl"
        # But in practice, we check HOST_UNREACHABLE first in is_connection_lost_error
        assert not PatternMatcher.matches(text, PatternCategory.SSL_ERROR)
    
    def test_all_categories_have_patterns(self):
        """Test that all categories have at least one pattern defined."""
        for category in PatternCategory:
            patterns = PatternMatcher.get_patterns(category)
            assert len(patterns) > 0, f"Category {category} has no patterns defined"
