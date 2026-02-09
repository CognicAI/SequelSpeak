import pytest
import sys
import os

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path

from utils.security import mask_connection_url

def test_mask_simple_url():
    url = "postgres://user:password@localhost:5432/db"
    expected = "postgres://user:******@localhost:5432/db"
    assert mask_connection_url(url) == expected

def test_mask_complex_password():
    # Password with special chars must be encoded if they include delimiters like @ or :
    # p@$$word!#:123 -> p%40$$word!%23:123
    url = "postgresql://user:p%40$$word!%23:123@host.com/db"
    expected = "postgresql://user:******@host.com/db"
    assert mask_connection_url(url) == expected

def test_mask_embedded_in_error():
    msg = "Connection failed: FATAL: password authentication failed for postgres://user:secret@192.168.1.1"
    expected = "Connection failed: FATAL: password authentication failed for postgres://user:******@192.168.1.1"
    assert mask_connection_url(msg) == expected

def test_no_password():
    url = "postgres://user@localhost/db"
    # No password provided, should remain as is (regex expects :password)
    assert mask_connection_url(url) == url

def test_non_postgres_url():
    url = "http://user:pass@example.com"
    # Logic returns url if "postgres" not in string (if strictly checking scheme)
    # or regex checks specifically for postgres.
    # Our regex is r"(postgres(?:ql)?://..."
    # So http should not be masked.
    assert mask_connection_url(url) == url

def test_empty_input():
    assert mask_connection_url(None) == "None"
    assert mask_connection_url("") == ""
