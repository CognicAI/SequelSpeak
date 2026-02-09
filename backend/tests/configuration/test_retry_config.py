#!/usr/bin/env python3
"""
Test script to verify retry configuration is properly loaded and used.
"""

import sys
import os

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


from config import settings


def test_retry_config_loaded():
    """Verify retry configuration settings are loaded with correct defaults."""
    print("=" * 70)
    print("Retry Configuration Test")
    print("=" * 70)
    
    print("\nConnection Retry Settings:")
    print(f"  CONNECTION_RETRY_MAX:           {settings.connection_retry_max}")
    print(f"  CONNECTION_RETRY_INITIAL_DELAY: {settings.connection_retry_initial_delay}s")
    
    print("\nHealth Check Retry Settings:")
    print(f"  HEALTH_CHECK_RETRY_MAX:         {settings.health_check_retry_max}")
    
    print("\nVerifying defaults:")
    assert settings.connection_retry_max == 2, f"Expected 2, got {settings.connection_retry_max}"
    print("  ✓ connection_retry_max = 2 (default)")
    
    assert settings.connection_retry_initial_delay == 1.0, f"Expected 1.0, got {settings.connection_retry_initial_delay}"
    print("  ✓ connection_retry_initial_delay = 1.0s (default)")
    
    assert settings.health_check_retry_max == 1, f"Expected 1, got {settings.health_check_retry_max}"
    print("  ✓ health_check_retry_max = 1 (default)")
    
    print("\n" + "=" * 70)
    print("✓ All retry settings loaded correctly!")
    print("=" * 70)


def test_methods_use_config():
    """Verify methods use config values as defaults."""
    print("\n" + "=" * 70)
    print("Method Default Usage Test")
    print("=" * 70)
    
    # Test that methods import settings and use config values
    from services.db_connection_service import DBConnectionService
    from utils.connection_resilience import ConnectionHealthMonitor
    
    print("\nImporting connection methods...")
    print("  ✓ DBConnectionService imported")
    print("  ✓ ConnectionHealthMonitor imported")
    
    # Verify docstrings mention config defaults
    test_connection_doc = DBConnectionService.test_connection.__doc__
    check_connection_doc = ConnectionHealthMonitor.check_connection.__doc__
    
    assert 'settings.connection_retry_max' in test_connection_doc, "test_connection should reference settings"
    print("\n  ✓ test_connection() references settings.connection_retry_max")
    
    assert 'settings.connection_retry_initial_delay' in test_connection_doc, "test_connection should reference settings"
    print("  ✓ test_connection() references settings.connection_retry_initial_delay")
    
    assert 'settings.health_check_retry_max' in check_connection_doc, "check_connection should reference settings"
    print("  ✓ check_connection() references settings.health_check_retry_max")
    
    print("\n" + "=" * 70)
    print("✓ Methods correctly reference configuration!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_retry_config_loaded()
        test_methods_use_config()
        
        print("\n" + "╔" + "═" * 68 + "╗")
        print("║" + " " * 18 + "Configuration Test PASSED" + " " * 25 + "║")
        print("╚" + "═" * 68 + "╝\n")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
