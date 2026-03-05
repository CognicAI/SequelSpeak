"""
Async connection pool manager for PostgreSQL database connections.

Provides a singleton ConnectionPoolManager that maintains one AsyncConnectionPool
per unique database URL, ensuring efficient connection reuse across async requests.
"""

import logging
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, List
from psycopg_pool import AsyncConnectionPool
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class PoolStats:
    """
    Statistics for a connection pool.
    
    Attributes:
        pool_key: Hashed pool identifier (for security, not the raw URL)
        size: Current total size of the pool (all connections)
        available: Number of connections available for use
        min_size: Configured minimum pool size
        max_size: Configured maximum pool size
        timeout: Configured connection timeout in seconds
        is_open: Whether the pool is currently open
        is_full: Whether the pool has reached maximum capacity
    """
    pool_key: str
    size: int
    available: int
    min_size: int
    max_size: int
    timeout: int
    is_open: bool
    is_full: bool


class ConnectionPoolManager:
    """
    Manages async connection pools for different database URLs.
    
    Thread-safe and event-loop-safe singleton that maintains a pool per unique
    connection URL. Pools are created lazily on first access and cached for reuse.
    
    Usage:
        pool_manager = ConnectionPoolManager()
        pool = await pool_manager.get_pool(connection_url)
        async with pool.connection() as conn:
            # Use connection
            pass
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pools = {}  
            cls._instance._initialized = False
        return cls._instance
    
    async def get_pool(
        self,
        connection_url: str,
        min_size: int = None,
        max_size: int = None,
        timeout: int = None
    ) -> AsyncConnectionPool:
        """
        Get or create an async connection pool for the given URL.
        
        Args:
            connection_url: Database connection URL
            min_size: Minimum pool size (default: from settings.db_pool_min_size)
            max_size: Maximum pool size (default: from settings.db_pool_max_size)
            timeout: Connection timeout (default: from settings.db_pool_timeout)
            
        Returns:
            AsyncConnectionPool instance
            
        Note:
            Uses URL hash as key to avoid storing raw credentials in memory.
            Pools are created lazily and cached for the lifetime of the application.
        """
        # Use configuration defaults if not specified
        min_size = min_size or settings.db_pool_min_size
        max_size = max_size or settings.db_pool_max_size
        timeout = timeout or settings.db_pool_timeout
        
        # Use URL hash as key (don't store raw URLs in memory)
        pool_key = str(hash(connection_url))
        
        # Fast path: check if pool exists without holding lock
        async with self._lock:
            if pool_key in self._pools:
                return self._pools[pool_key]
        
        # Slow path: create pool
        logger.info(
            f"Creating async connection pool (min_size={min_size}, "
            f"max_size={max_size}, timeout={timeout}s)"
        )
        
        pool = None
        try:
            # Create the pool with open=False
            pool = AsyncConnectionPool(
                connection_url,
                min_size=min_size,
                max_size=max_size,
                timeout=timeout,
                open=False
            )
            
            # Open the pool (async I/O - done outside lock for better concurrency)
            await pool.open()
            
            # Store the opened pool
            async with self._lock:
                # Double-check: another task might have created it while we were opening
                if pool_key in self._pools:
                    # Another task created the pool, close ours and return existing
                    try:
                        await pool.close()
                    except Exception as close_err:
                        logger.warning(f"Failed to close duplicate pool: {close_err}")
                    return self._pools[pool_key]
                
                self._pools[pool_key] = pool
                logger.info(f"Connection pool created and opened successfully (pool_key={pool_key[:8]}...)")
                return pool
                
        except Exception as e:
            # Critical: If pool.open() failed, ensure we close the pool to prevent resource leak
            if pool is not None and not pool.closed:
                try:
                    await pool.close()
                    logger.warning(f"Closed pool after failed open (pool_key={pool_key[:8]}...)")
                except Exception as close_err:
                    logger.error(f"Failed to close pool after open error: {close_err}")
            
            # Re-raise the original exception
            logger.error(f"Failed to create/open connection pool: {e}")
            raise
    
    async def get_pool_stats(self, connection_url: str) -> Optional[PoolStats]:
        """
        Get statistics for a specific connection pool.
        
        Args:
            connection_url: Database connection URL
            
        Returns:
            PoolStats object with pool metrics, or None if pool doesn't exist
        """
        pool_key = str(hash(connection_url))
        
        async with self._lock:
            if pool_key not in self._pools:
                return None
            
            pool = self._pools[pool_key]
            
            # Get pool statistics from psycopg_pool
            # Note: AsyncConnectionPool doesn't expose detailed stats directly,
            # so we use the properties available
            try:
                # Pool size properties
                pool_size = pool._pool.size if hasattr(pool, '_pool') else 0
                pool_available = pool._pool.available if hasattr(pool, '_pool') else 0
                
                return PoolStats(
                    pool_key=pool_key[:8] + "...",  # Truncated for security
                    size=pool_size,
                    available=pool_available,
                    min_size=pool.min_size,
                    max_size=pool.max_size,
                    timeout=pool.timeout,
                    is_open=not pool.closed,
                    is_full=(pool_size >= pool.max_size)
                )
            except AttributeError:
                # Fallback if internal structure changes
                logger.warning(f"Could not access pool statistics for {pool_key[:8]}...")
                return PoolStats(
                    pool_key=pool_key[:8] + "...",
                    size=0,
                    available=0,
                    min_size=pool.min_size,
                    max_size=pool.max_size,
                    timeout=pool.timeout,
                    is_open=not pool.closed,
                    is_full=False
                )
    
    async def get_all_pools_stats(self) -> List[PoolStats]:
        """
        Get statistics for all connection pools.
        
        Returns:
            List of PoolStats objects for all active pools
        """
        async with self._lock:
            stats_list = []
            
            for pool_key, pool in self._pools.items():
                try:
                    pool_size = pool._pool.size if hasattr(pool, '_pool') else 0
                    pool_available = pool._pool.available if hasattr(pool, '_pool') else 0
                    
                    stats = PoolStats(
                        pool_key=pool_key[:8] + "...",
                        size=pool_size,
                        available=pool_available,
                        min_size=pool.min_size,
                        max_size=pool.max_size,
                        timeout=pool.timeout,
                        is_open=not pool.closed,
                        is_full=(pool_size >= pool.max_size)
                    )
                    stats_list.append(stats)
                except AttributeError:
                    logger.warning(f"Could not access pool statistics for {pool_key[:8]}...")
            
            return stats_list
    
    async def get_active_connection_count(self, connection_url: str) -> int:
        """
        Get the number of active (in-use) connections for a specific URL.
        
        Args:
            connection_url: Database connection URL
            
        Returns:
            Number of active connections (size - available)
        """
        stats = await self.get_pool_stats(connection_url)
        if stats is None:
            return 0
        
        # Active connections = total connections - available connections
        return stats.size - stats.available
    
    async def get_total_active_connections(self) -> int:
        """
        Get the total number of active connections across all pools.
        
        Returns:
            Total number of active connections
        """
        all_stats = await self.get_all_pools_stats()
        return sum(stats.size - stats.available for stats in all_stats)
    
    async def is_pool_at_capacity(self, connection_url: str) -> bool:
        """
        Check if a connection pool is at maximum capacity.
        
        Args:
            connection_url: Database connection URL
            
        Returns:
            True if pool is at max capacity, False otherwise
        """
        stats = await self.get_pool_stats(connection_url)
        if stats is None:
            return False
        
        return stats.is_full
    
    async def get_pool_count(self) -> int:
        """
        Get the total number of connection pools.
        
        Returns:
            Number of active connection pools
        """
        async with self._lock:
            return len(self._pools)
    
    async def close_all(self):
        """
        Close all connection pools gracefully.
        
        Should be called during application shutdown to ensure all database
        connections are properly closed and resources are released.
        """
        async with self._lock:
            if not self._pools:
                logger.info("No connection pools to close")
                return
            
            logger.info(f"Closing {len(self._pools)} connection pool(s)...")
            
            for pool_key, pool in list(self._pools.items()):
                try:
                    # Skip if already closed
                    if pool.closed:
                        logger.debug(f"Pool {pool_key[:8]}... already closed, skipping")
                        continue
                    
                    # Add timeout to prevent hanging during shutdown
                    await asyncio.wait_for(pool.close(), timeout=5.0)
                    logger.info(f"Connection pool closed (pool_key={pool_key[:8]}...)")
                except asyncio.CancelledError:
                    # Handle cancellation gracefully during shutdown
                    logger.debug(f"Pool {pool_key[:8]}... close cancelled, marking as closed")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout closing pool {pool_key[:8]}..., forcing close")
                except Exception as e:
                    logger.error(f"Error closing pool {pool_key[:8]}...: {e}")
            
            self._pools.clear()
            logger.info("All connection pools closed successfully")


# Global singleton instance
pool_manager = ConnectionPoolManager()
