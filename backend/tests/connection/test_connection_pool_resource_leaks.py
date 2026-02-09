"""
Tests for connection pool resource leak prevention and lifecycle management.

This test suite verifies that the connection pool manager correctly handles:
- Pool cleanup on failed open() to prevent resource leaks
- Concurrent pool creation without duplicates
- Proper pool closure during shutdown
"""

import sys
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from services.connection_pool import ConnectionPoolManager


@pytest.mark.asyncio
class TestPoolResourceLeaks:
    """Test prevention of resource leaks in pool management."""
    
    async def test_pool_closed_on_failed_open(self):
        """
        CRITICAL FIX: Verify pool is closed if open() fails to prevent resource leak.
        
        Scenario:
        1. Pool is created successfully
        2. pool.open() raises an exception (e.g., network error)
        3. Pool should be closed to release resources
        4. Exception should be re-raised to caller
        """
        manager = ConnectionPoolManager()
        
        # Clear existing pools
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool_instance = AsyncMock()
            mock_pool_instance.closed = False
            mock_pool_instance.open = AsyncMock(side_effect=Exception("Network connection failed"))
            mock_pool_instance.close = AsyncMock()
            MockPool.return_value = mock_pool_instance
            
            # Attempt to get pool (should fail)
            with pytest.raises(Exception, match="Network connection failed"):
                await manager.get_pool(url)
            
            # CRITICAL: Verify pool.close() was called after failed open
            mock_pool_instance.close.assert_called_once()
            
            # Verify pool was not stored in manager
            async with manager._lock:
                assert len(manager._pools) == 0
    
    async def test_pool_already_closed_on_failed_open(self):
        """Verify no error if pool is already closed when open() fails."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool_instance = AsyncMock()
            mock_pool_instance.closed = True  # Already closed
            mock_pool_instance.open = AsyncMock(side_effect=Exception("Network error"))
            mock_pool_instance.close = AsyncMock()
            MockPool.return_value = mock_pool_instance
            
            # Attempt to get pool (should fail)
            with pytest.raises(Exception, match="Network error"):
                await manager.get_pool(url)
            
            # pool.close() should NOT be called since pool.closed = True
            mock_pool_instance.close.assert_not_called()
    
    async def test_pool_close_error_handled_gracefully(self):
        """Verify errors during pool.close() after failed open don't mask original error."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool_instance = AsyncMock()
            mock_pool_instance.closed = False
            mock_pool_instance.open = AsyncMock(side_effect=Exception("Open failed"))
            mock_pool_instance.close = AsyncMock(side_effect=Exception("Close failed"))
            MockPool.return_value = mock_pool_instance
            
            # Should raise the ORIGINAL exception from open(), not the close() exception
            with pytest.raises(Exception, match="Open failed"):
                await manager.get_pool(url)


@pytest.mark.asyncio
class TestConcurrentPoolCreation:
    """Test pool creation under concurrent access."""
    
    async def test_concurrent_get_pool_no_duplicates(self):
        """
        PERFORMANCE FIX: Verify concurrent calls to get_pool don't create duplicate pools.
        
        Scenario:
        1. Multiple tasks try to get pool for same URL simultaneously
        2. Due to async I/O during pool.open(), all tasks may create pools initially
        3. But only one pool should be stored in manager (double-check pattern)
        4. Duplicate pools should be closed
        """
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        # Track number of pool creations and closures
        pools_created = []
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            def create_mock_pool(*args, **kwargs):
                mock_pool = AsyncMock()
                mock_pool.min_size = kwargs.get('min_size', 1)
                mock_pool.max_size = kwargs.get('max_size', 5)
                mock_pool.timeout = kwargs.get('timeout', 30)
                mock_pool.closed = False
                
                # Simulate slow pool opening to create race condition
                async def slow_open():
                    await asyncio.sleep(0.01)
                
                mock_pool.open = slow_open
                mock_pool.close = AsyncMock()
                
                pools_created.append(mock_pool)
                return mock_pool
            
            MockPool.side_effect = create_mock_pool
            
            # Make 10 concurrent requests
            tasks = [manager.get_pool(url) for _ in range(10)]
            pools = await asyncio.gather(*tasks)
            
            # All tasks should receive a pool (may be same or different due to race)
            assert len(pools) == 10
            assert all(p is not None for p in pools)
            
            # CRITICAL: Only one pool should be stored in manager despite race conditions
            async with manager._lock:
                assert len(manager._pools) == 1, f"Expected 1 pool stored, got {len(manager._pools)}"
            
            # If multiple pools were created, all except one should have been closed
            if len(pools_created) > 1:
                closed_count = sum(1 for pool in pools_created if pool.close.called)
                assert closed_count == len(pools_created) - 1, \
                    f"Expected {len(pools_created) - 1} duplicate pools to be closed, got {closed_count}"
    
    async def test_duplicate_pool_closed_on_race_condition(self):
        """Verify duplicate pool is closed if created during race condition."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        # Simulate race condition: two pools created simultaneously
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            pools_created = []
            
            def create_mock_pool(*args, **kwargs):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 5
                mock_pool.timeout = 30
                mock_pool.closed = False
                mock_pool.close = AsyncMock()
                pools_created.append(mock_pool)
                return mock_pool
            
            MockPool.side_effect = create_mock_pool
            
            # Start two get_pool calls that overlap
            task1 = asyncio.create_task(manager.get_pool(url))
            await asyncio.sleep(0.01)  # Small delay
            task2 = asyncio.create_task(manager.get_pool(url))
            
            pool1, pool2 = await asyncio.gather(task1, task2)
            
            # Both tasks should return the same pool
            assert pool1 is pool2
            
            # If two pools were created, one should have been closed
            if len(pools_created) == 2:
                # One of the pools should have been closed
                assert any(pool.close.called for pool in pools_created)


@pytest.mark.asyncio
class TestPoolClosureChecks:
    """Test proper handling of pool closure."""
    
    async def test_close_all_skips_already_closed_pools(self):
        """
        IMPROVEMENT: Verify close_all() doesn't attempt to close already-closed pools.
        
        Scenario:
        1. Create multiple pools
        2. Some pools are already closed
        3. close_all() should skip closed pools without error
        """
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            # Create 3 mock pools
            mock_pools = []
            for i in range(3):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 5
                mock_pool.timeout = 30
                mock_pool.closed = (i == 1)  # Middle pool is already closed
                mock_pool.close = AsyncMock()
                mock_pools.append(mock_pool)
            
            MockPool.side_effect = mock_pools
            
            # Create pools
            await manager.get_pool("postgresql://user:pass@host1/db")
            await manager.get_pool("postgresql://user:pass@host2/db")
            await manager.get_pool("postgresql://user:pass@host3/db")
            
            # Close all pools
            await manager.close_all()
            
            # Verify only non-closed pools were closed
            assert mock_pools[0].close.called  # First pool should be closed
            assert not mock_pools[1].close.called  # Second pool was already closed, skip
            assert mock_pools[2].close.called  # Third pool should be closed
    
    async def test_close_all_handles_close_errors_gracefully(self):
        """Verify close_all() continues closing other pools even if one fails."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            # Create 3 mock pools
            mock_pools = []
            for i in range(3):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 5
                mock_pool.timeout = 30
                mock_pool.closed = False
                
                # Middle pool will fail to close
                if i == 1:
                    mock_pool.close = AsyncMock(side_effect=Exception("Close failed"))
                else:
                    mock_pool.close = AsyncMock()
                
                mock_pools.append(mock_pool)
            
            MockPool.side_effect = mock_pools
            
            # Create pools
            await manager.get_pool("postgresql://user:pass@host1/db")
            await manager.get_pool("postgresql://user:pass@host2/db")
            await manager.get_pool("postgresql://user:pass@host3/db")
            
            # Close all pools (should not raise exception)
            await manager.close_all()
            
            # Verify all pools were attempted to be closed
            assert mock_pools[0].close.called
            assert mock_pools[1].close.called
            assert mock_pools[2].close.called
            
            # Verify pools dict was cleared despite error
            async with manager._lock:
                assert len(manager._pools) == 0
    
    async def test_close_all_with_timeout_continues_cleanup(self):
        """Verify close_all() continues closing other pools when one times out."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            # Create 3 mock pools
            mock_pools = []
            for i in range(3):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 5
                mock_pool.timeout = 30
                mock_pool.closed = False
                
                # Middle pool will timeout
                if i == 1:
                    async def slow_close():
                        await asyncio.sleep(10)  # Longer than 5s timeout
                    mock_pool.close = slow_close
                else:
                    mock_pool.close = AsyncMock()
                
                mock_pools.append(mock_pool)
            
            MockPool.side_effect = mock_pools
            
            # Create pools
            await manager.get_pool("postgresql://user:pass@host1/db")
            await manager.get_pool("postgresql://user:pass@host2/db")
            await manager.get_pool("postgresql://user:pass@host3/db")
            
            # Close all pools (should handle timeout gracefully)
            await manager.close_all()
            
            # Verify pools dict was cleared despite timeout
            async with manager._lock:
                assert len(manager._pools) == 0


@pytest.mark.asyncio
class TestPoolLifecycleScenarios:
    """Test complete pool lifecycle scenarios."""
    
    async def test_full_lifecycle_with_failed_open_and_retry(self):
        """
        Integration test: Verify complete lifecycle with failure and retry.
        
        Scenario:
        1. First attempt to create pool fails during open()
        2. Pool is properly closed (no leak)
        3. Second attempt succeeds
        4. Pool is used normally
        5. Pool is closed cleanly during shutdown
        """
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        url = "postgresql://user:pass@localhost:5432/testdb"
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            # First attempt: fails
            mock_pool_fail = AsyncMock()
            mock_pool_fail.closed = False
            mock_pool_fail.open = AsyncMock(side_effect=Exception("Network error"))
            mock_pool_fail.close = AsyncMock()
            
            # Second attempt: succeeds
            mock_pool_success = AsyncMock()
            mock_pool_success.closed = False
            mock_pool_success.open = AsyncMock()
            mock_pool_success.close = AsyncMock()
            mock_pool_success.min_size = 1
            mock_pool_success.max_size = 5
            mock_pool_success.timeout = 30
            
            MockPool.side_effect = [mock_pool_fail, mock_pool_success]
            
            # First attempt fails
            with pytest.raises(Exception, match="Network error"):
                await manager.get_pool(url)
            
            # Verify first pool was closed
            mock_pool_fail.close.assert_called_once()
            
            # Second attempt succeeds
            pool = await manager.get_pool(url)
            assert pool is mock_pool_success
            
            # Pool is stored
            async with manager._lock:
                assert len(manager._pools) == 1
            
            # Clean shutdown
            await manager.close_all()
            
            # Verify successful pool was closed
            mock_pool_success.close.assert_called_once()
            
            # Verify no pools remain
            async with manager._lock:
                assert len(manager._pools) == 0
