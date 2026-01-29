"""
Input Validation Module for Database Connection Security

Provides validation functions to detect and block potentially dangerous
patterns in database connection URLs before they are processed.

Security checks include:
- Null byte injection detection
- SQL injection pattern detection  
- Command injection pattern detection
- Control character detection
- URL length limits
"""

import re
from dataclasses import dataclass
from typing import Optional


# Maximum allowed URL length (prevents buffer-style attacks)
MAX_URL_LENGTH = 2048


@dataclass
class ValidationResult:
    """Result of input validation check."""
    is_valid: bool
    error_message: Optional[str] = None
    error_type: Optional[str] = None


def contains_null_bytes(value: str) -> bool:
    """
    Check if string contains null bytes (raw or URL-encoded).
    
    Null bytes can be used to truncate strings in some systems,
    potentially bypassing validation or causing unexpected behavior.
    
    Args:
        value: String to check
        
    Returns:
        True if null bytes are detected, False otherwise
    """
    if not value:
        return False
    
    # Check for raw null byte
    if '\x00' in value:
        return True
    
    # Check for URL-encoded null byte (case-insensitive)
    if '%00' in value.lower():
        return True
    
    return False


def contains_sql_injection_patterns(value: str) -> bool:
    """
    Check for common SQL injection patterns.
    
    While database connection URLs shouldn't be directly injectable,
    blocking these patterns provides defense-in-depth against
    URL manipulation attacks.
    
    Args:
        value: String to check
        
    Returns:
        True if SQL injection patterns detected, False otherwise
    """
    if not value:
        return False
    
    value_lower = value.lower()
    
    # Detect SQL line comments in suspicious contexts (e.g., after whitespace or quotes)
    # to avoid rejecting legitimate values like "my--database.example.com".
    if re.search(r'(^|[\s\'";])--(\s|$)', value_lower):
        return True
    
    # SQL comment and injection patterns that could be used to manipulate parsing
    sql_patterns = [
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
    ]
    
    for pattern in sql_patterns:
        if pattern in value_lower:
            return True
    
    return False


def contains_command_injection_patterns(value: str) -> bool:
    """
    Check for command/shell injection patterns.
    
    These patterns could be dangerous if the connection URL is ever
    passed to a shell command or improperly escaped.
    
    Note: URL-encoded special characters (like %7C for pipe) are allowed
    since they represent legitimate password characters.
    
    Args:
        value: String to check
        
    Returns:
        True if command injection patterns detected, False otherwise
    """
    if not value:
        return False
    
    # Shell metacharacters and command substitution patterns
    # Note: We're careful not to flag legitimate URL characters
    dangerous_patterns = [
        '$(',           # Command substitution
        '`',            # Backtick command substitution
        '&&',           # Shell AND operator
        '||',           # Shell OR operator
        '\n', '\r\n',   # Newlines (command injection via line breaks)
        '>${', '>$(', '<$(',  # Redirection with substitution
    ]
    
    for pattern in dangerous_patterns:
        if pattern in value:
            return True
    
    # Check for raw pipe character '|' - but allow URL-encoded %7C
    # Raw pipes in URLs are suspicious; legitimate pipes in passwords should be URL-encoded
    if '|' in value:
        # Check if this could be a command injection pattern
        # Pattern: something | command
        pipe_idx = value.find('|')
        # If there's content after the pipe that looks like a command, block it
        after_pipe = value[pipe_idx+1:pipe_idx+15].strip().lower()
        command_indicators = ['cat', 'rm', 'ls', 'echo', 'wget', 'curl', 'bash', 
                              'sh', 'python', 'perl', 'nc', 'netcat', 'grep', 'awk']
        if any(after_pipe.startswith(cmd) for cmd in command_indicators):
            return True
        # Also block if pipe appears to be used for shell piping (space before and after)
        if pipe_idx > 0 and pipe_idx < len(value) - 1:
            before = value[pipe_idx-1]
            after = value[pipe_idx+1] if pipe_idx+1 < len(value) else ''
            # Pattern like: " | " is very suspicious
            if before == ' ' and after == ' ':
                return True
    
    # Check for semicolon NOT followed by a valid URL query param pattern
    # Allow: ?sslmode=require;connect_timeout=10 (query params)
    # Block: ;rm -rf or ; DROP (command injection)
    if ';' in value:
        # If there's a semicolon outside of valid query parameter context
        # Valid: ...?param1=val;param2=val or ...?param=val1;val2
        # Currently, we only treat semicolons as suspicious when there is no query string.
        query_start = value.find('?')
        if query_start == -1:
            # No query string, semicolons in the main URL are suspicious.
            value_upper = value.upper()
            value_lower = value.lower()
            search_pos = -1
            while True:
                semicolon_pos = value.find(';', search_pos + 1)
                if semicolon_pos == -1:
                    break
                # Skip URL-encoded semicolon which is considered okay.
                if '%3B' in value_upper[:semicolon_pos+3]:
                    search_pos = semicolon_pos
                    continue
                # Check what comes after the semicolon
                after_semicolon = value_lower[semicolon_pos+1:semicolon_pos+10].strip()
                # Common command injection indicators
                if any(cmd in after_semicolon for cmd in ['rm', 'cat', 'ls', 'echo', 'wget', 'curl', 'bash', 'sh', 'python', 'perl', 'drop', 'delete']):
                    return True
                search_pos = semicolon_pos
    
    return False


def contains_control_characters(value: str) -> bool:
    """
    Check for ASCII control characters (except common whitespace).
    
    Control characters (ASCII 0-31, 127) can cause unexpected behavior
    in string processing and should generally not appear in URLs.
    
    Args:
        value: String to check
        
    Returns:
        True if dangerous control characters detected, False otherwise
    """
    if not value:
        return False
    
    for char in value:
        code = ord(char)
        # Allow: tab (9), newline (10), carriage return (13)
        # Note: Newline (10) and carriage return (13) are permitted here because
        # command injection detection is responsible for rejecting any inputs where
        # those characters are used in a dangerous way (e.g., to break commands).
        if code < 32 and code not in (9, 10, 13):
            return True
        # DEL character
        if code == 127:
            return True
    
    return False


def validate_url_length(value: str) -> bool:
    """
    Check if URL length is within acceptable limits.
    
    Args:
        value: URL string to check
        
    Returns:
        True if length is acceptable, False if too long
    """
    if not value:
        return True
    
    return len(value) <= MAX_URL_LENGTH


def validate_connection_url(url: str) -> ValidationResult:
    """
    Perform comprehensive security validation on a database connection URL.
    
    This is the main entry point for URL validation. It runs all security
    checks and returns a ValidationResult indicating whether the URL is
    safe to process.
    
    Args:
        url: The database connection URL to validate
        
    Returns:
        ValidationResult with is_valid=True if safe, or error details if not
    """
    # Handle None/empty
    if url is None:
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL cannot be empty.",
            error_type="empty_input"
        )
    
    if not isinstance(url, str):
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL must be a string.",
            error_type="invalid_type"
        )
    
    url = url.strip()
    
    if not url:
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL cannot be empty.",
            error_type="empty_input"
        )
    
    # Check URL length
    if not validate_url_length(url):
        return ValidationResult(
            is_valid=False,
            error_message=f"Connection URL exceeds maximum length of {MAX_URL_LENGTH} characters.",
            error_type="length_exceeded"
        )
    
    # Check for null bytes
    if contains_null_bytes(url):
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL contains invalid characters.",
            error_type="null_byte"
        )
    
    # Check for control characters
    if contains_control_characters(url):
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL contains invalid control characters.",
            error_type="control_char"
        )
    
    # Check for SQL injection patterns
    if contains_sql_injection_patterns(url):
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL contains invalid patterns.",
            error_type="sql_injection"
        )
    
    # Check for command injection patterns
    if contains_command_injection_patterns(url):
        return ValidationResult(
            is_valid=False,
            error_message="Connection URL contains invalid characters.",
            error_type="command_injection"
        )
    
    return ValidationResult(is_valid=True)


def sanitize_for_logging(value: str) -> str:
    """
    Sanitize a value for safe logging by removing/replacing dangerous characters.
    
    This is a utility function for creating log-safe versions of input strings.
    It does NOT make the string safe for use in database operations.
    
    Args:
        value: String to sanitize
        
    Returns:
        Sanitized string safe for logging
    """
    if not value or not isinstance(value, str):
        return str(value) if value is not None else ""
    
    # Replace null bytes
    result = value.replace('\x00', '<NUL>')
    
    # Replace other control characters
    sanitized = []
    for char in result:
        code = ord(char)
        if code < 32 and code not in (9, 10, 13):
            sanitized.append(f'<{code:02X}>')
        elif code == 127:
            sanitized.append('<DEL>')
        else:
            sanitized.append(char)
    
    return ''.join(sanitized)
