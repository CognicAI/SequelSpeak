"""
Tests for timestamp tracking in ConnectionHealthMonitor.

This test suite verifies that the health monitor correctly tracks:
- When health checks are performed
- When the connection became unhealthy
- How long the connection has been down
- Time since last successful connection
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

from utils.connection_resilience import ConnectionHealthMonitor, ConnectionState
from schemas.errors import ErrorCode


@pytest.mark.asyncio
class TestTimestampTracking:
    """Test timestamp tracking in ConnectionHealthMonitor."""
    
    async def test_initial_timestamps_are_none(self):
        """Verify all timestamps are None on initialization."""
        monitor = ConnectionHealthMonitor()
        
        assert await monitor.get_last_check_time() is None
        assert await monitor.get_last_healthy_time() is None
        assert await monitor.get_first_failure_time() is None
    
    async def test_mark_healthy_updates_last_healthy_time(self):
        """Verify mark_healthy sets last_healthy_time."""
        monitor = ConnectionHealthMonitor()
        
        before_time = time.time()
        await monitor.mark_healthy()
        after_time = time.time()
        
        last_healthy = await monitor.get_last_healthy_time()
        assert last_healthy is not None
        assert before_time <= last_healthy <= after_time
    
    async def test_mark_unhealthy_sets_first_failure_time(self):
        """Verify mark_unhealthy sets first_failure_time on initial failure."""
        monitor = ConnectionHealthMonitor()
        
        before_time = time.time()
        await monitor.mark_unhealthy()
        after_time = time.time()
        
        first_failure = await monitor.get_first_failure_time()
        assert first_failure is not None
        assert before_time <= first_failure <= after_time
    
    async def test_mark_unhealthy_preserves_first_failure_time(self):
        """Verify multiple mark_unhealthy calls don't overwrite first_failure_time."""
        monitor = ConnectionHealthMonitor()
        
        # First failure
        await monitor.mark_unhealthy()
        first_failure_time = await monitor.get_first_failure_time()
        
        # Wait a bit
        await asyncio.sleep(0.1)
        
        # Second failure
        await monitor.mark_unhealthy()
        second_failure_time = await monitor.get_first_failure_time()
        
        # Should be the same time (not updated)
        assert first_failure_time == second_failure_time
    
    async def test_mark_healthy_clears_first_failure_time(self):
        """Verify mark_healthy clears first_failure_time when recovering."""
        monitor = ConnectionHealthMonitor()
        
        # Mark unhealthy
        await monitor.mark_unhealthy()
        assert await monitor.get_first_failure_time() is not None
        
        # Mark healthy (recovery)
        await monitor.mark_healthy()
        assert await monitor.get_first_failure_time() is None
    
    async def test_downtime_duration_calculation(self):
        """Verify downtime duration is calculated correctly."""
        monitor = ConnectionHealthMonitor()
        
        # Mark unhealthy
        await monitor.mark_unhealthy()
        
        # Wait a known duration
        await asyncio.sleep(0.2)
        
        # Check downtime
        downtime = await monitor.get_downtime_duration()
        assert downtime is not None
        # Allow some tolerance for timing precision
        assert 0.15 <= downtime <= 0.3
    
    async def test_downtime_duration_none_when_healthy(self):
        """Verify downtime_duration returns None when connection is healthy."""
        monitor = ConnectionHealthMonitor()
        
        # Never failed
        assert await monitor.get_downtime_duration() is None
        
        # Fail then recover
        await monitor.mark_unhealthy()
        await monitor.mark_healthy()
        
        # Should be None after recovery
        assert await monitor.get_downtime_duration() is None
    
    async def test_time_since_last_check(self):
        """Verify time_since_last_check calculates correctly."""
        monitor = ConnectionHealthMonitor()
        
        # Mock the connection pool
        with patch('services.connection_pool.pool_manager') as mock_pool_manager:
            # Setup mock pool and connection
            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            
            mock_pool_manager.get_pool.return_value = mock_pool
            mock_pool.connection.return_value.__aenter__.return_value = mock_conn
            mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1,)
            
            # Perform a health check
            await monitor.check_connection("postgres://user:pass@host/db", timeout=5, max_retries=0)
            
            # Wait a bit
            await asyncio.sleep(0.1)
            
            # Check time since last check
            time_since = await monitor.get_time_since_last_check()
            assert time_since is not None
            assert 0.08 <= time_since <= 0.15
    
    async def test_time_since_last_check_none_initially(self):
        """Verify time_since_last_check returns None if no check performed."""
        monitor = ConnectionHealthMonitor()
        
        assert await monitor.get_time_since_last_check() is None
    
    async def test_time_since_last_healthy(self):
        """Verify time_since_last_healthy calculates correctly."""
        monitor = ConnectionHealthMonitor()
        
        # Mark healthy
        await monitor.mark_healthy()
        
        # Wait a bit
        await asyncio.sleep(0.1)
        
        # Check time since last healthy
        time_since = await monitor.get_time_since_last_healthy()
        assert time_since is not None
        assert 0.08 <= time_since <= 0.15
    
    async def test_time_since_last_healthy_none_initially(self):
        """Verify time_since_last_healthy returns None if never healthy."""
        monitor = ConnectionHealthMonitor()
        
        assert await monitor.get_time_since_last_healthy() is None
    
    async def test_check_connection_updates_last_check_time(self):
        """Verify check_connection updates last_check_time."""
        monitor = ConnectionHealthMonitor()
        
        # Mock the connection pool to simulate a successful check
        with patch('services.connection_pool.pool_manager') as mock_pool_manager:
            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            
            mock_pool_manager.get_pool.return_value = mock_pool
            mock_pool.connection.return_value.__aenter__.return_value = mock_conn
            mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1,)
            
            before_time = time.time()
            await monitor.check_connection("postgres://user:pass@host/db", timeout=5, max_retries=0)
            after_time = time.time()
            
            last_check = await monitor.get_last_check_time()
            assert last_check is not None
            assert before_time <= last_check <= after_time
    
    async def test_check_connection_updates_last_check_time_on_failure(self):
        """Verify check_connection updates last_check_time even on failure."""
        monitor = ConnectionHealthMonitor()
        
        # Mock the connection pool to simulate a failed check
        with patch('services.connection_pool.pool_manager') as mock_pool_manager:
            import psycopg
            mock_pool_manager.get_pool.side_effect = psycopg.OperationalError("Connection failed")
            
            before_time = time.time()
            result = await monitor.check_connection("postgres://user:pass@host/db", timeout=5, max_retries=0)
            after_time = time.time()
            
            # Should fail
            assert not result.success
            
            # But should still update last_check_time
            last_check = await monitor.get_last_check_time()
            assert last_check is not None
            assert before_time <= last_check <= after_time


@pytest.mark.asyncio
class TestTimestampScenarios:
    """Test realistic timestamp tracking scenarios."""
    
    async def test_scenario_database_goes_down(self):
        """
        Scenario: Database goes down at 10:00 AM
        Verify we can determine when it went down and how long it's been down.
        """
        monitor = ConnectionHealthMonitor()
        
        # Initial healthy state
        await monitor.mark_healthy()
        healthy_time = await monitor.get_last_healthy_time()
        
        # Simulate time passing (database still healthy)
        await asyncio.sleep(0.05)
        
        # Database goes down
        await monitor.mark_unhealthy()
        failure_start = await monitor.get_first_failure_time()
        
        # Verify we can determine when it went down
        assert failure_start is not None
        assert failure_start > healthy_time
        
        # Simulate time passing (database still down)
        await asyncio.sleep(0.1)
        
        # Additional failures
        await monitor.mark_unhealthy()
        await monitor.mark_unhealthy()
        
        # Verify we can calculate downtime
        downtime = await monitor.get_downtime_duration()
        assert downtime is not None
        assert downtime >= 0.1  # At least the sleep duration
        
        # Verify consecutive failures incremented
        assert await monitor.get_consecutive_failures() == 3
        
        # Verify first_failure_time hasn't changed (locked to initial failure)
        assert await monitor.get_first_failure_time() == failure_start
    
    async def test_scenario_database_recovery(self):
        """
        Scenario: Database recovers after being down
        Verify timestamps reset correctly on recovery.
        """
        monitor = ConnectionHealthMonitor()
        
        # Database goes down
        await monitor.mark_unhealthy()
        first_failure = await monitor.get_first_failure_time()
        
        # Wait during downtime
        await asyncio.sleep(0.1)
        
        # Database recovers
        await monitor.mark_healthy()
        
        # Verify recovery state
        assert await monitor.get_state() == ConnectionState.CONNECTED
        assert await monitor.get_consecutive_failures() == 0
        assert await monitor.get_first_failure_time() is None  # Cleared on recovery
        
        # Verify we have a new healthy timestamp
        new_healthy_time = await monitor.get_last_healthy_time()
        assert new_healthy_time is not None
        assert new_healthy_time > first_failure  # After the failure
    
    async def test_scenario_intermittent_failures(self):
        """
        Scenario: Database has intermittent connection issues
        Verify timestamps track each failure cycle correctly.
        """
        monitor = ConnectionHealthMonitor()
        
        # First failure cycle
        await monitor.mark_unhealthy()
        first_cycle_failure = await monitor.get_first_failure_time()
        await asyncio.sleep(0.05)
        await monitor.mark_healthy()
        
        # Wait a bit
        await asyncio.sleep(0.05)
        
        # Second failure cycle
        await monitor.mark_unhealthy()
        second_cycle_failure = await monitor.get_first_failure_time()
        
        # Should be different times (new failure cycle)
        assert second_cycle_failure != first_cycle_failure
        assert second_cycle_failure > first_cycle_failure
    
    async def test_scenario_health_check_timing(self):
        """
        Scenario: Monitor when health checks are performed
        Verify we can determine time until next check.
        """
        monitor = ConnectionHealthMonitor()
        
        # Mock the connection pool for health checks
        with patch('services.connection_pool.pool_manager') as mock_pool_manager:
            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            
            mock_pool_manager.get_pool.return_value = mock_pool
            mock_pool.connection.return_value.__aenter__.return_value = mock_conn
            mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1,)
            
            # Perform first check
            await monitor.check_connection("postgres://user:pass@host/db", timeout=5, max_retries=0)
            first_check = await monitor.get_last_check_time()
            
            # Wait
            await asyncio.sleep(0.1)
            
            # Perform second check
            await monitor.check_connection("postgres://user:pass@host/db", timeout=5, max_retries=0)
            second_check = await monitor.get_last_check_time()
            
            # Verify checks are tracked
            assert second_check > first_check
            assert (second_check - first_check) >= 0.1


@pytest.mark.asyncio
class TestTimestampThreadSafety:
    """Test timestamp tracking is thread-safe."""
    
    async def test_concurrent_mark_operations(self):
        """Verify concurrent mark operations don't corrupt timestamps."""
        monitor = ConnectionHealthMonitor()
        
        # Perform concurrent mark operations
        await asyncio.gather(
            monitor.mark_healthy(),
            monitor.mark_unhealthy(),
            monitor.mark_healthy(),
            monitor.mark_unhealthy(),
        )
        
        # Verify we have valid timestamps (no corruption)
        last_healthy = await monitor.get_last_healthy_time()
        first_failure = await monitor.get_first_failure_time()
        
        # Both should be set (operations interleaved)
        assert last_healthy is not None
        assert first_failure is not None
    
    async def test_concurrent_timestamp_reads(self):
        """Verify concurrent timestamp reads are safe."""
        monitor = ConnectionHealthMonitor()
        
        await monitor.mark_unhealthy()
        
        # Perform concurrent reads
        results = await asyncio.gather(
            monitor.get_last_check_time(),
            monitor.get_last_healthy_time(),
            monitor.get_first_failure_time(),
            monitor.get_downtime_duration(),
            monitor.get_time_since_last_check(),
            monitor.get_time_since_last_healthy(),
        )
        
        # Should complete without errors (no race conditions)
        assert len(results) == 6
