"""
Centralized pattern matching for security validation and error detection.

This module consolidates all pattern definitions used across the application
to eliminate duplication and provide a single source of truth for:
- SQL injection detection
- Command injection detection
- Connection error classification
- Security validation

Usage:
    from utils.patterns import PatternMatcher, PatternCategory
    
    # Check for SQL injection
    if PatternMatcher.matches(user_input, PatternCategory.SQL_INJECTION):
        raise SecurityError("SQL injection detected")
    
    # Get all matching patterns
    matches = PatternMatcher.find_matches(error_msg, PatternCategory.SSL_ERROR)
"""

import re
from enum import Enum
from typing import List, Dict


class PatternCategory(str, Enum):
    """Categories of patterns for different detection purposes."""
    
    # Security validation patterns
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    
    # Database error classification patterns
    CONNECTION_LOST = "connection_lost"
    SSL_ERROR = "ssl_error"
    AUTH_ERROR = "auth_error"
    DATABASE_NOT_FOUND = "database_not_found"
    TIMEOUT_ERROR = "timeout_error"
    HOST_UNREACHABLE = "host_unreachable"


class PatternMatcher:
    """
    Centralized pattern matching for security and error detection.
    
    All patterns are defined in a single location for maintainability.
    Supports case-insensitive matching and pattern discovery.
    """
    
    # Pattern definitions for each category
    PATTERNS: Dict[PatternCategory, List[str]] = {
        # SQL Injection Patterns
        PatternCategory.SQL_INJECTION: [
            '/*',           # SQL block comment start
            '*/',           # SQL block comment end
            ';--',          # Statement terminator + comment
            "'; ",          # Quote + statement terminator
            '"; ',          # Double quote + statement terminator
            'union select', # UNION-based injection
            'or 1=1',       # Boolean-based injection
            'and 1=1',      # Boolean-based injection
            'drop table',   # DDL command
            'drop database',# DDL command
            'truncate ',    # DDL command
            'delete from',  # DML command
            'insert into',  # DML command
            'update ',      # DML command (with space to avoid false positive on 'updated')
        ],
        
        # Command Injection Patterns
        PatternCategory.COMMAND_INJECTION: [
            '$(',           # Command substitution
            '`',            # Backtick command substitution
            '&&',           # Shell AND operator
            '||',           # Shell OR operator
            '\n',           # Newlines (command injection via line breaks)
            '\r\n',         # Carriage return + newline
            '>${',          # Redirection with substitution
            '>$(',          # Redirection with command substitution
            '<$(',          # Input redirection with command substitution
        ],
        
        # Connection Lost Patterns (runtime failure)
        PatternCategory.CONNECTION_LOST: [
            "connection closed",
            "server closed the connection unexpectedly",
            "connection reset",
            "broken pipe",
            "connection terminated",
            "connection already closed",
            "connection is closed",
            "connection has been closed",
            "connection was closed",
            "lost connection",
            "server has gone away",
            "connection timed out during operation",
            "connection dropped",
        ],
        
        # SSL/TLS Error Patterns
        PatternCategory.SSL_ERROR: [
            "ssl error",
            "ssl connection",
            "ssl handshake",
            "certificate verify",
            "certificate validation",
            "certificate_verify_failed",
            "tlsv1",
            "ssl_error",
            "certificate expired",
            "certificate invalid",
            "self-signed certificate",
        ],
        
        # Authentication Error Patterns
        PatternCategory.AUTH_ERROR: [
            "password authentication failed",
            "authentication failed",
            "no pg_hba.conf entry",
            "permission denied",
        ],
        
        # Database Not Found Patterns
        PatternCategory.DATABASE_NOT_FOUND: [
            "does not exist.*database",
            "database.*does not exist",
        ],
        
        # Timeout Error Patterns
        PatternCategory.TIMEOUT_ERROR: [
            "timeout expired",
            "timed out",
            "connection timeout",
        ],
        
        # Host Unreachable Patterns
        PatternCategory.HOST_UNREACHABLE: [
            "ssl syscall",  # SSL-related network issues
            "could not connect to server",
            "connection refused",
            "could not translate host name",
            "network is unreachable",
        ],
    }
    
    @classmethod
    def matches(
        cls, 
        text: str, 
        category: PatternCategory,
        case_sensitive: bool = False
    ) -> bool:
        """
        Check if text matches any pattern in the specified category.
        
        Supports both simple string matching and regex patterns.
        Patterns containing ".*" are treated as regex.
        
        Args:
            text: The text to check for patterns
            category: The pattern category to match against
            case_sensitive: Whether to perform case-sensitive matching (default: False)
            
        Returns:
            True if any pattern matches, False otherwise
            
        Example:
            >>> PatternMatcher.matches("DROP TABLE users", PatternCategory.SQL_INJECTION)
            True
        """
        if not text:
            return False
        
        patterns = cls.PATTERNS.get(category, [])
        compare_text = text if case_sensitive else text.lower()
        
        for pattern in patterns:
            # Regex pattern detection
            if ".*" in pattern:
                try:
                    if re.search(pattern, compare_text):
                        return True
                except re.error:
                    # Fall back to simple string matching if regex is invalid
                    if pattern in compare_text:
                        return True
            else:
                # Simple string matching
                if pattern in compare_text:
                    return True
        
        return False
    
    @classmethod
    def find_matches(cls, text: str, category: PatternCategory) -> List[str]:
        """
        Return all patterns from the category that match the text.
        
        Useful for debugging and logging which specific patterns were detected.
        
        Args:
            text: The text to check for patterns
            category: The pattern category to search
            
        Returns:
            List of matching patterns (empty if none match)
            
        Example:
            >>> matches = PatternMatcher.find_matches(
            ...     "connection closed unexpectedly", 
            ...     PatternCategory.CONNECTION_LOST
            ... )
            >>> print(matches)
            ['connection closed', 'server closed the connection unexpectedly']
        """
        if not text:
            return []
        
        patterns = cls.PATTERNS.get(category, [])
        text_lower = text.lower()
        
        return [p for p in patterns if p in text_lower]
    
    @classmethod
    def get_patterns(cls, category: PatternCategory) -> List[str]:
        """
        Get all patterns for a specific category.
        
        Useful for testing and documentation purposes.
        
        Args:
            category: The pattern category
            
        Returns:
            List of patterns in the category
        """
        return cls.PATTERNS.get(category, []).copy()
    
    @classmethod
    def add_pattern(cls, category: PatternCategory, pattern: str) -> None:
        """
        Add a new pattern to a category at runtime.
        
        Args:
            category: The pattern category
            pattern: The pattern to add
            
        Note:
            Use sparingly - prefer updating PATTERNS dict for permanent additions
        """
        if category not in cls.PATTERNS:
            cls.PATTERNS[category] = []
        
        if pattern not in cls.PATTERNS[category]:
            cls.PATTERNS[category].append(pattern)
    
    @classmethod
    def matches_any_category(cls, text: str, categories: List[PatternCategory]) -> bool:
        """
        Check if text matches patterns in any of the specified categories.
        
        Args:
            text: The text to check
            categories: List of categories to check against
            
        Returns:
            True if matches any pattern in any category
            
        Example:
            >>> categories = [PatternCategory.SQL_INJECTION, PatternCategory.COMMAND_INJECTION]
            >>> PatternMatcher.matches_any_category("DROP TABLE; $(rm -rf /)", categories)
            True
        """
        return any(cls.matches(text, category) for category in categories)
