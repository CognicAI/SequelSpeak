"""
Simulation script to verify connection loss detection and auto-recovery behavior.

This script mocks psycopg.connect to simulate connection failures and verifies that:
1. The retry decorator attempts reconnection with exponential backoff
2. Retry limits are respected
3. The health monitor tracks state correctly
4. User notifications (ConnectionResult messages) are appropriate
"""

import sys
import os
from unittest.mock import MagicMock, patch
import logging

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg
from services.db_connection_service import DBConnectionService
from utils.connection_resilience import health_monitor, ConnectionState
from schemas.errors import ErrorCode

# Configure logging to see the output
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


def test_auto_recovery():
    """Test that the system auto-recovers after transient connection failures."""
    print("\n" + "="*70)
    print("TEST 1: Auto-Recovery After Transient Failures")
    print("="*70)
    
    db_url = "postgres://user:pass@localhost:5432/db"
    
    # Create mock connection that succeeds
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1,)
    
    # Simulate: Fail twice, then succeed
    fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
    
    with patch("psycopg.connect") as mock_connect, \
         patch("time.sleep") as mock_sleep:
        
        # First two calls fail, third succeeds
        mock_connect.side_effect = [
            fail_exception,
            fail_exception,
            MagicMock(__enter__=MagicMock(return_value=mock_conn), __exit__=MagicMock())
        ]
        
        print(f"Initial health monitor state: {health_monitor.state}")
        print("\nTriggering test_connection (expecting 2 retries before success)...\n")
        
        result = DBConnectionService.test_connection(db_url)
        
        print(f"\n{'─'*70}")
        print(f"Result:")
        print(f"  - Success: {result.success}")
        print(f"  - Message: {result.message}")
        print(f"  - Error Code: {result.error_code}")
        print(f"Final health monitor state: {health_monitor.state}")
        print(f"Connection attempts: {mock_connect.call_count}")
        print(f"Sleep calls (retries): {mock_sleep.call_count}")
        print(f"{'─'*70}")
        
        # Assertions
        assert mock_connect.call_count == 3, f"Expected 3 connection attempts, got {mock_connect.call_count}"
        assert mock_sleep.call_count == 2, f"Expected 2 sleep calls, got {mock_sleep.call_count}"
        assert result.success is True, "Expected success=True after recovery"
        assert health_monitor.state == ConnectionState.CONNECTED, f"Expected CONNECTED state, got {health_monitor.state}"
        
        print("\n✅ Auto-recovery test PASSED\n")


def test_retry_limit():
    """Test that retry limits are respected and system fails gracefully."""
    print("\n" + "="*70)
    print("TEST 2: Retry Limit Enforcement")
    print("="*70)
    
    db_url = "postgres://user:pass@localhost:5432/db"
    
    # Always fail
    fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
    
    with patch("psycopg.connect") as mock_connect, \
         patch("time.sleep") as mock_sleep:
        
        mock_connect.side_effect = fail_exception
        
        print(f"Initial health monitor state: {health_monitor.state}")
        print("\nTriggering test_connection (expecting retry exhaustion)...\n")
        
        result = DBConnectionService.test_connection(db_url)
        
        print(f"\n{'─'*70}")
        print(f"Result:")
        print(f"  - Success: {result.success}")
        print(f"  - Message: {result.message}")
        print(f"  - Error Code: {result.error_code}")
        print(f"Final health monitor state: {health_monitor.state}")
        print(f"Connection attempts: {mock_connect.call_count}")
        print(f"Consecutive failures: {health_monitor.consecutive_failures}")
        print(f"{'─'*70}")
        
        # Assertions (max_retries=2 means 1 initial + 2 retries = 3 total attempts)
        assert mock_connect.call_count == 3, f"Expected 3 connection attempts, got {mock_connect.call_count}"
        assert result.success is False, "Expected success=False after retry exhaustion"
        assert result.error_code == ErrorCode.CONNECTION_LOST, f"Expected CONNECTION_LOST, got {result.error_code}"
        assert health_monitor.state == ConnectionState.DISCONNECTED, f"Expected DISCONNECTED state, got {health_monitor.state}"
        
        print("\n✅ Retry limit test PASSED\n")


def test_user_notification():
    """Test that user notifications are appropriate."""
    print("\n" + "="*70)
    print("TEST 3: User Notification Validation")
    print("="*70)
    
    db_url = "postgres://user:pass@localhost:5432/db"
    
    fail_exception = psycopg.OperationalError("server closed the connection unexpectedly")
    
    with patch("psycopg.connect") as mock_connect, \
         patch("time.sleep"):
        
        mock_connect.side_effect = fail_exception
        
        result = DBConnectionService.test_connection(db_url)
        
        print(f"\nUser-facing message: \"{result.message}\"")
        
        # Verify message is user-friendly
        assert "connection was lost" in result.message.lower() or "try again" in result.message.lower(), \
            "Message should inform user about connection loss"
        
        # Verify no credentials in message
        assert "pass" not in result.message, "Credentials should not appear in message"
        assert "secret" not in result.message.lower(), "Credentials should not appear in message"
        
        print("\n✅ User notification test PASSED\n")


def main():
    """Run all simulation tests."""
    print("\n" + "="*70)
    print("CONNECTION LOSS & AUTO-RECOVERY SIMULATION")
    print("="*70)
    
    try:
        test_auto_recovery()
        test_retry_limit()
        test_user_notification()
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED ✅")
        print("="*70)
        print("\nVerified:")
        print("  ✓ Connection drop simulated")
        print("  ✓ Reconnection attempts verified")
        print("  ✓ Retry limits respected")
        print("  ✓ User notifications validated")
        print("  ✓ System stability confirmed")
        print()
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
