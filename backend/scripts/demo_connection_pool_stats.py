#!/usr/bin/env python3
"""
Demo script to showcase connection pool statistics and tracking.

This script demonstrates the connection pool monitoring capabilities added
to solve the connection tracking issue:
- Track active connections per database URL
- Monitor connection pool capacity
- View statistics across all pools
- Prevent resource exhaustion

Run this script to see connection pool tracking in action:
    python scripts/demo_connection_pool_stats.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from services.connection_pool import ConnectionPoolManager, PoolStats


def print_header(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")


def print_pool_stats(stats: PoolStats):
    """Print pool statistics in a formatted way."""
    print(f"\nPool: {stats.pool_key}")
    print(f"  Size: {stats.size} connections (min: {stats.min_size}, max: {stats.max_size})")
    print(f"  Available: {stats.available} connections")
    print(f"  Active: {stats.size - stats.available} connections")
    print(f"  Timeout: {stats.timeout}s")
    print(f"  Status: {'OPEN' if stats.is_open else 'CLOSED'}")
    print(f"  Capacity: {'FULL' if stats.is_full else f'{stats.size}/{stats.max_size}'}")


async def demo_single_pool_monitoring():
    """
    Scenario 1: Monitor a single connection pool
    
    Demonstrates tracking connections for a single database URL.
    """
    print_header("SCENARIO 1: Single Pool Monitoring")
    print("\nMonitoring connections to a single database...")
    
    manager = ConnectionPoolManager()
    
    # Clear existing pools
    async with manager._lock:
        manager._pools.clear()
    
    with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
        # Create mock pool
        mock_pool = AsyncMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.timeout = 30
        mock_pool.closed = False
        
        # Start with 2 connections (min_size)
        mock_internal_pool = MagicMock()
        mock_internal_pool.size = 2
        mock_internal_pool.available = 2
        mock_pool._pool = mock_internal_pool
        
        MockPool.return_value = mock_pool
        
        test_url = "postgres://user:pass@prod-db.example.com:5432/myapp"
        
        # Create pool
        print(f"\n[Step 1] Creating connection pool...")
        await manager.get_pool(test_url)
        
        # Get initial stats
        stats = await manager.get_pool_stats(test_url)
        print("\nInitial pool state:")
        print_pool_stats(stats)
        
        # Simulate connections being used
        print("\n[Step 2] Simulating load - connections being used...")
        mock_internal_pool.available = 0  # All 2 connections in use
        
        active_count = await manager.get_active_connection_count(test_url)
        print(f"\nActive connections: {active_count}")
        
        # Pool grows under load
        print("\n[Step 3] Pool grows to handle more requests...")
        mock_internal_pool.size = 5  # Grew from 2 to 5
        mock_internal_pool.available = 1  # 4 active, 1 available
        
        stats = await manager.get_pool_stats(test_url)
        print_pool_stats(stats)
        
        # Check if pool is at capacity
        at_capacity = await manager.is_pool_at_capacity(test_url)
        print(f"\nIs pool at capacity? {at_capacity}")
        
        # Pool reaches maximum
        print("\n[Step 4] Pool reaches maximum capacity...")
        mock_internal_pool.size = 10  # At max_size
        mock_internal_pool.available = 0  # All in use
        
        stats = await manager.get_pool_stats(test_url)
        print_pool_stats(stats)
        
        at_capacity = await manager.is_pool_at_capacity(test_url)
        print(f"\nIs pool at capacity? {at_capacity}")
        print("\n⚠️  WARNING: Pool is full - new requests will be queued or timeout!")


async def demo_multiple_pool_monitoring():
    """
    Scenario 2: Monitor multiple connection pools
    
    Demonstrates tracking connections across multiple database URLs.
    """
    print_header("SCENARIO 2: Multiple Pool Monitoring")
    print("\nMonitoring connections across multiple databases...")
    
    manager = ConnectionPoolManager()
    
    async with manager._lock:
        manager._pools.clear()
    
    with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
        def create_mock_pool(size, available, min_size, max_size):
            mock_pool = AsyncMock()
            mock_pool.min_size = min_size
            mock_pool.max_size = max_size
            mock_pool.timeout = 30
            mock_pool.closed = False
            
            mock_internal_pool = MagicMock()
            mock_internal_pool.size = size
            mock_internal_pool.available = available
            mock_pool._pool = mock_internal_pool
            
            return mock_pool
        
        # Create mock pools for different databases
        mock_pools = [
            create_mock_pool(5, 2, 2, 10),   # Prod DB: 3 active
            create_mock_pool(10, 0, 2, 10),  # Analytics DB: 10 active (full)
            create_mock_pool(2, 2, 2, 5),    # Cache DB: 0 active
        ]
        MockPool.side_effect = mock_pools
        
        # Create pools
        db_urls = [
            "postgres://user:pass@prod-db.example.com:5432/myapp",
            "postgres://user:pass@analytics-db.example.com:5432/analytics",
            "postgres://user:pass@cache-db.example.com:5432/cache"
        ]
        
        print("\n[Step 1] Creating connection pools for multiple databases...")
        for url in db_urls:
            await manager.get_pool(url)
        
        # Get pool count
        pool_count = await manager.get_pool_count()
        print(f"\nTotal connection pools: {pool_count}")
        
        # Get stats for all pools
        print("\n[Step 2] Getting statistics for all pools...")
        all_stats = await manager.get_all_pools_stats()
        
        db_names = ["Production DB", "Analytics DB", "Cache DB"]
        for i, stats in enumerate(all_stats):
            print(f"\n{db_names[i]}:")
            print_pool_stats(stats)
        
        # Check capacity for each pool
        print("\n[Step 3] Checking capacity status...")
        for i, url in enumerate(db_urls):
            at_capacity = await manager.is_pool_at_capacity(url)
            active_count = await manager.get_active_connection_count(url)
            print(f"\n{db_names[i]}:")
            print(f"  Active connections: {active_count}")
            print(f"  At capacity: {'YES ⚠️' if at_capacity else 'NO ✓'}")
        
        # Get total active connections
        print("\n[Step 4] Calculating global statistics...")
        total_active = await manager.get_total_active_connections()
        print(f"\nTotal active connections across all pools: {total_active}")


async def demo_resource_limits():
    """
    Scenario 3: Preventing resource exhaustion
    
    Demonstrates using pool statistics to implement connection limits.
    """
    print_header("SCENARIO 3: Resource Limit Enforcement")
    print("\nUsing pool statistics to prevent resource exhaustion...")
    
    manager = ConnectionPoolManager()
    
    async with manager._lock:
        manager._pools.clear()
    
    with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
        mock_pool = AsyncMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 5
        mock_pool.timeout = 30
        mock_pool.closed = False
        
        mock_internal_pool = MagicMock()
        mock_internal_pool.size = 4
        mock_internal_pool.available = 1
        mock_pool._pool = mock_internal_pool
        
        MockPool.return_value = mock_pool
        
        test_url = "postgres://user:pass@prod-db.example.com:5432/myapp"
        
        print("\n[Step 1] Pool is under heavy load...")
        await manager.get_pool(test_url)
        
        stats = await manager.get_pool_stats(test_url)
        print_pool_stats(stats)
        
        # Check if we should allow new connections
        MAX_ACTIVE_CONNECTIONS = 3
        
        print(f"\n[Step 2] Checking connection limit (max: {MAX_ACTIVE_CONNECTIONS})...")
        active_count = await manager.get_active_connection_count(test_url)
        
        print(f"\nActive connections: {active_count}")
        print(f"Configured limit: {MAX_ACTIVE_CONNECTIONS}")
        
        if active_count >= MAX_ACTIVE_CONNECTIONS:
            print("\n❌ REJECTED: Too many active connections")
            print("   Action: Request queued or returning error")
            print("   Message: 'Too many active connections - please wait'")
        else:
            print("\n✓ ALLOWED: Connection limit not reached")
            print("   Action: Processing request")
        
        # Also check if pool is at capacity
        print("\n[Step 3] Checking pool capacity...")
        at_capacity = await manager.is_pool_at_capacity(test_url)
        
        if at_capacity:
            print("\n⚠️  WARNING: Pool is at maximum capacity")
            print("   This means no more connections can be created")
            print("   New requests will queue until connections are released")
        else:
            print("\n✓ Pool has room to grow if needed")


async def demo_use_case():
    """
    Scenario 4: Real-world use case
    
    Demonstrates the desired functionality from the issue description.
    """
    print_header("SCENARIO 4: Real-World Use Case")
    print("\nImplementing connection limit check in application code...")
    
    manager = ConnectionPoolManager()
    
    async with manager._lock:
        manager._pools.clear()
    
    with patch('services.connection_pool.AsyncConnectionPool') as MockPool:
        mock_pool = AsyncMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.timeout = 30
        mock_pool.closed = False
        
        mock_internal_pool = MagicMock()
        mock_internal_pool.size = 8
        mock_internal_pool.available = 1
        mock_pool._pool = mock_internal_pool
        
        MockPool.return_value = mock_pool
        
        url = "postgres://user:pass@prod-db.example.com:5432/myapp"
        await manager.get_pool(url)
        
        print("\nApplication code example:")
        print("```python")
        print("# Check active connections before processing request")
        print("active_connections = await pool_manager.get_active_connection_count(url)")
        print("MAX_CONNECTIONS = 5")
        print("")
        print("if active_connections > MAX_CONNECTIONS:")
        print("    return ConnectionResult(")
        print("        success=False,")
        print("        message='Too many active connections - please wait',")
        print("        error_code=ErrorCode.CONNECTION_ERROR")
        print("    )")
        print("```")
        
        print("\nExecuting check...")
        active_count = await manager.get_active_connection_count(url)
        MAX_CONNECTIONS = 5
        
        print(f"\nCurrent active connections: {active_count}")
        print(f"Configured maximum: {MAX_CONNECTIONS}")
        
        if active_count > MAX_CONNECTIONS:
            print("\n❌ Result: Request REJECTED")
            print("   Reason: Too many active connections")
            print("   Action: Return error to user")
        else:
            print("\n✓ Result: Request ACCEPTED")
            print("   Reason: Within connection limits")
            print("   Action: Process request normally")


async def main():
    """Run all demonstration scenarios."""
    print("\n" + "=" * 60)
    print("CONNECTION POOL STATISTICS & TRACKING DEMONSTRATION")
    print("Solution to: No mechanism to track active connections")
    print("=" * 60)
    
    await demo_single_pool_monitoring()
    await demo_multiple_pool_monitoring()
    await demo_resource_limits()
    await demo_use_case()
    
    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nThe ConnectionPoolManager now provides:")
    print("✓ get_pool_stats(url) - Get statistics for a specific pool")
    print("✓ get_all_pools_stats() - Get statistics for all pools")
    print("✓ get_active_connection_count(url) - Count active connections per URL")
    print("✓ get_total_active_connections() - Count total active connections")
    print("✓ is_pool_at_capacity(url) - Check if pool is full")
    print("✓ get_pool_count() - Get total number of pools")
    print("\nPoolStats includes:")
    print("  • size - Total connections in pool")
    print("  • available - Idle connections ready for use")
    print("  • min_size, max_size - Pool size configuration")
    print("  • is_full - Whether pool is at maximum capacity")
    print("  • is_open - Whether pool is operational")
    print("\nUse cases:")
    print("  • Prevent resource exhaustion with connection limits")
    print("  • Monitor database load across multiple databases")
    print("  • Detect when pools are at capacity")
    print("  • Track connection usage patterns")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
