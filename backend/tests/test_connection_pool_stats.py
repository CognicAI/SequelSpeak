"""
Tests for connection pool statistics and tracking.

This test suite verifies the new connection pool monitoring capabilities:
- Get statistics for individual pools
- Get statistics for all pools
- Track active connection counts
- Check if pools are at capacity
- Monitor pool count across multiple URLs
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.connection_pool import ConnectionPoolManager, PoolStats


class TestPoolStatsDataclass:
    """Test the PoolStats dataclass structure."""
    
    def test_pool_stats_creation(self):
        """Verify PoolStats can be created with all required fields."""
        stats = PoolStats(
            pool_key="abc123...",
            size=5,
            available=2,
            min_size=1,
            max_size=10,
            timeout=30,
            is_open=True,
            is_full=False
        )
        
        assert stats.pool_key == "abc123..."
        assert stats.size == 5
        assert stats.available == 2
        assert stats.min_size == 1
        assert stats.max_size == 10
        assert stats.timeout == 30
        assert stats.is_open is True
        assert stats.is_full is False
    
    def test_pool_stats_is_full_detection(self):
        """Verify is_full flag correctly indicates capacity."""
        # Not full
        stats = PoolStats(
            pool_key="test...",
            size=5,
            available=2,
            min_size=1,
            max_size=10,
            timeout=30,
            is_open=True,
            is_full=False
        )
        assert stats.is_full is False
        
        # At capacity
        stats_full = PoolStats(
            pool_key="test...",
            size=10,
            available=0,
            min_size=1,
            max_size=10,
            timeout=30,
            is_open=True,
            is_full=True
        )
        assert stats_full.is_full is True


@pytest.mark.asyncio
class TestGetPoolStats:
    """Test getting statistics for individual connection pools."""
    
    async def test_get_stats_for_nonexistent_pool(self):
        """Verify get_pool_stats returns None for nonexistent pool."""
        manager = ConnectionPoolManager()
        
        # Clear any existing pools
        async with manager._lock:
            manager._pools.clear()
        
        stats = await manager.get_pool_stats("postgres://user:pass@host/db")
        assert stats is None
    
    async def test_get_stats_returns_pool_stats(self):
        """Verify get_pool_stats returns PoolStats for existing pool."""
        manager = ConnectionPoolManager()
        
        # Clear existing pools
        async with manager._lock:
            manager._pools.clear()
        
        # Mock pool with statistics
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # Mock internal pool stats
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 3
            mock_internal_pool.available = 1
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            # Create pool
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            # Get stats
            stats = await manager.get_pool_stats(test_url)
            
            assert stats is not None
            assert isinstance(stats, PoolStats)
            assert stats.size == 3
            assert stats.available == 1
            assert stats.min_size == 1
            assert stats.max_size == 5
            assert stats.timeout == 30
            assert stats.is_open is True
    
    async def test_pool_key_is_truncated_for_security(self):
        """Verify pool_key in stats is truncated to avoid exposing full hash."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 2
            mock_internal_pool.available = 2
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            stats = await manager.get_pool_stats(test_url)
            
            # Verify key is truncated (8 chars + "...")
            assert stats.pool_key.endswith("...")
            assert len(stats.pool_key) == 11  # 8 chars + "..."


@pytest.mark.asyncio
class TestGetAllPoolsStats:
    """Test getting statistics for all connection pools."""
    
    async def test_get_all_stats_empty_pools(self):
        """Verify get_all_pools_stats returns empty list when no pools exist."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        all_stats = await manager.get_all_pools_stats()
        assert all_stats == []
    
    async def test_get_all_stats_single_pool(self):
        """Verify get_all_pools_stats returns list with one pool."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 2
            mock_internal_pool.available = 1
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            await manager.get_pool("postgres://user:pass@host1/db")
            
            all_stats = await manager.get_all_pools_stats()
            
            assert len(all_stats) == 1
            assert all_stats[0].size == 2
            assert all_stats[0].available == 1
    
    async def test_get_all_stats_multiple_pools(self):
        """Verify get_all_pools_stats returns all pools."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            # Create multiple mock pools
            def create_mock_pool(size, available):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 5
                mock_pool.timeout = 30
                mock_pool.closed = False
                
                mock_internal_pool = MagicMock()
                mock_internal_pool.size = size
                mock_internal_pool.available = available
                mock_pool._pool = mock_internal_pool
                
                return mock_pool
            
            # Setup side_effect to return different pools
            mock_pools = [
                create_mock_pool(2, 1),
                create_mock_pool(3, 0),
                create_mock_pool(1, 1)
            ]
            MockPool.side_effect = mock_pools
            
            # Create multiple pools
            await manager.get_pool("postgres://user:pass@host1/db")
            await manager.get_pool("postgres://user:pass@host2/db")
            await manager.get_pool("postgres://user:pass@host3/db")
            
            all_stats = await manager.get_all_pools_stats()
            
            assert len(all_stats) == 3
            
            # Verify each pool has stats
            sizes = [stats.size for stats in all_stats]
            assert 2 in sizes
            assert 3 in sizes
            assert 1 in sizes


@pytest.mark.asyncio
class TestActiveConnectionCount:
    """Test tracking active connection counts."""
    
    async def test_active_count_for_nonexistent_pool(self):
        """Verify active count is 0 for nonexistent pool."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        count = await manager.get_active_connection_count("postgres://user:pass@host/db")
        assert count == 0
    
    async def test_active_count_calculation(self):
        """Verify active count is calculated as (size - available)."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # 5 total connections, 2 available = 3 active
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 5
            mock_internal_pool.available = 2
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            active_count = await manager.get_active_connection_count(test_url)
            
            assert active_count == 3  # 5 - 2 = 3
    
    async def test_active_count_all_in_use(self):
        """Verify active count when all connections are in use."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # 5 total, 0 available = 5 active
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 5
            mock_internal_pool.available = 0
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            active_count = await manager.get_active_connection_count(test_url)
            
            assert active_count == 5
    
    async def test_active_count_all_available(self):
        """Verify active count when all connections are available."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # 3 total, 3 available = 0 active
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 3
            mock_internal_pool.available = 3
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            active_count = await manager.get_active_connection_count(test_url)
            
            assert active_count == 0


@pytest.mark.asyncio
class TestTotalActiveConnections:
    """Test tracking total active connections across all pools."""
    
    async def test_total_active_no_pools(self):
        """Verify total active is 0 when no pools exist."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        total = await manager.get_total_active_connections()
        assert total == 0
    
    async def test_total_active_single_pool(self):
        """Verify total active with single pool."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 5
            mock_internal_pool.available = 2
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            await manager.get_pool("postgres://user:pass@host/db")
            
            total = await manager.get_total_active_connections()
            
            assert total == 3  # 5 - 2
    
    async def test_total_active_multiple_pools(self):
        """Verify total active sums across multiple pools."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            def create_mock_pool(size, available):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = 10
                mock_pool.timeout = 30
                mock_pool.closed = False
                
                mock_internal_pool = MagicMock()
                mock_internal_pool.size = size
                mock_internal_pool.available = available
                mock_pool._pool = mock_internal_pool
                
                return mock_pool
            
            # Pool 1: 5 size, 2 available = 3 active
            # Pool 2: 3 size, 1 available = 2 active
            # Pool 3: 2 size, 2 available = 0 active
            # Total: 5 active
            mock_pools = [
                create_mock_pool(5, 2),
                create_mock_pool(3, 1),
                create_mock_pool(2, 2)
            ]
            MockPool.side_effect = mock_pools
            
            await manager.get_pool("postgres://user:pass@host1/db")
            await manager.get_pool("postgres://user:pass@host2/db")
            await manager.get_pool("postgres://user:pass@host3/db")
            
            total = await manager.get_total_active_connections()
            
            assert total == 5  # 3 + 2 + 0


@pytest.mark.asyncio
class TestIsPoolAtCapacity:
    """Test checking if connection pool is at maximum capacity."""
    
    async def test_pool_at_capacity_nonexistent_pool(self):
        """Verify is_pool_at_capacity returns False for nonexistent pool."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        at_capacity = await manager.is_pool_at_capacity("postgres://user:pass@host/db")
        assert at_capacity is False
    
    async def test_pool_at_capacity_not_full(self):
        """Verify is_pool_at_capacity returns False when pool is not full."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 10
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # 5 connections out of max 10
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 5
            mock_internal_pool.available = 2
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            at_capacity = await manager.is_pool_at_capacity(test_url)
            
            assert at_capacity is False
    
    async def test_pool_at_capacity_full(self):
        """Verify is_pool_at_capacity returns True when pool is full."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 10
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # 10 connections = max 10 (full)
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 10
            mock_internal_pool.available = 0
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            at_capacity = await manager.is_pool_at_capacity(test_url)
            
            assert at_capacity is True


@pytest.mark.asyncio
class TestGetPoolCount:
    """Test getting the total number of connection pools."""
    
    async def test_pool_count_no_pools(self):
        """Verify pool count is 0 when no pools exist."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        count = await manager.get_pool_count()
        assert count == 0
    
    async def test_pool_count_single_pool(self):
        """Verify pool count with single pool."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            MockPool.return_value = mock_pool
            
            await manager.get_pool("postgres://user:pass@host/db")
            
            count = await manager.get_pool_count()
            
            assert count == 1
    
    async def test_pool_count_multiple_pools(self):
        """Verify pool count with multiple pools."""
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 1
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            MockPool.return_value = mock_pool
            
            await manager.get_pool("postgres://user:pass@host1/db")
            await manager.get_pool("postgres://user:pass@host2/db")
            await manager.get_pool("postgres://user:pass@host3/db")
            
            count = await manager.get_pool_count()
            
            assert count == 3


@pytest.mark.asyncio
class TestConnectionPoolScenarios:
    """Test realistic connection pool monitoring scenarios."""
    
    async def test_scenario_monitor_pool_usage(self):
        """
        Scenario: Monitor connection pool usage to prevent resource exhaustion.
        """
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            mock_pool = AsyncMock()
            mock_pool.min_size = 2
            mock_pool.max_size = 5
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            # Start with 2 connections (min_size)
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = 2
            mock_internal_pool.available = 2
            mock_pool._pool = mock_internal_pool
            
            MockPool.return_value = mock_pool
            
            test_url = "postgres://user:pass@host/db"
            await manager.get_pool(test_url)
            
            # Check initial state
            stats = await manager.get_pool_stats(test_url)
            assert stats.size == 2
            assert stats.available == 2
            assert not stats.is_full
            
            # Simulate connections being used
            mock_internal_pool.available = 0  # All in use
            
            active_count = await manager.get_active_connection_count(test_url)
            assert active_count == 2
            
            # Pool grows under load
            mock_internal_pool.size = 5  # Grew to max
            mock_internal_pool.available = 0  # All in use
            
            # Check if at capacity
            at_capacity = await manager.is_pool_at_capacity(test_url)
            assert at_capacity is True
            
            # Get updated stats
            stats = await manager.get_pool_stats(test_url)
            assert stats.is_full is True
            assert stats.size == 5
            assert stats.available == 0
    
    async def test_scenario_multiple_databases(self):
        """
        Scenario: Monitor connections across multiple databases.
        """
        manager = ConnectionPoolManager()
        
        async with manager._lock:
            manager._pools.clear()
        
        with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
            def create_mock_pool(size, available, max_size):
                mock_pool = AsyncMock()
                mock_pool.min_size = 1
                mock_pool.max_size = max_size
                mock_pool.timeout = 30
                mock_pool.closed = False
                
                mock_internal_pool = MagicMock()
                mock_internal_pool.size = size
                mock_internal_pool.available = available
                mock_pool._pool = mock_internal_pool
                
                return mock_pool
            
            # Database 1: 3/5 connections active (not full - size < max)
            # Database 2: 5/5 connections active (full)
            # Database 3: 0/5 connections active
            mock_pools = [
                create_mock_pool(3, 0, 5),  # DB1: 3 active (size=3, max=5, not full)
                create_mock_pool(5, 0, 5),  # DB2: 5 active (size=5, max=5, full)
                create_mock_pool(1, 1, 5),  # DB3: 0 active
            ]
            MockPool.side_effect = mock_pools
            
            db1_url = "postgres://user:pass@host1/db1"
            db2_url = "postgres://user:pass@host2/db2"
            db3_url = "postgres://user:pass@host3/db3"
            
            await manager.get_pool(db1_url)
            await manager.get_pool(db2_url)
            await manager.get_pool(db3_url)
            
            # Check pool count
            pool_count = await manager.get_pool_count()
            assert pool_count == 3
            
            # Check individual pools
            assert await manager.get_active_connection_count(db1_url) == 3
            assert await manager.get_active_connection_count(db2_url) == 5
            assert await manager.get_active_connection_count(db3_url) == 0
            
            # Check which pools are at capacity
            assert not await manager.is_pool_at_capacity(db1_url)
            assert await manager.is_pool_at_capacity(db2_url)
            assert not await manager.is_pool_at_capacity(db3_url)
            
            # Check total active connections
            total_active = await manager.get_total_active_connections()
            assert total_active == 8  # 3 + 5 + 0
