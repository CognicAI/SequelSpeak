"""
Async connection pool manager for PostgreSQL database connections.

Provides a singleton ConnectionPoolManager that maintains one AsyncConnectionPool
per unique database URL, ensuring efficient connection reuse across async requests.
"""

import logging
import asyncio
from psycopg_pool import AsyncConnectionPool
from config import settings

logger = logging.getLogger(__name__)


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
        
        async with self._lock:
            if pool_key not in self._pools:
                logger.info(
                    f"Creating async connection pool (min_size={min_size}, "
                    f"max_size={max_size}, timeout={timeout}s)"
                )
                
                # Create the pool with open=False, then open it explicitly
                pool = AsyncConnectionPool(
                    connection_url,
                    min_size=min_size,
                    max_size=max_size,
                    timeout=timeout,
                    open=False
                )
                
                # Open the pool (this is an async operation)
                await pool.open()
                
                self._pools[pool_key] = pool
                logger.info(f"Connection pool created and opened successfully (pool_key={pool_key[:8]}...)")
            
            return self._pools[pool_key]
    
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
                    # Add timeout to prevent hanging during shutdown
                    await asyncio.wait_for(pool.close(), timeout=5.0)
                    logger.info(f"Connection pool closed (pool_key={pool_key[:8]}...)")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout closing pool {pool_key[:8]}..., forcing close")
                except Exception as e:
                    logger.error(f"Error closing pool {pool_key[:8]}...: {e}")
            
            self._pools.clear()
            logger.info("All connection pools closed successfully")


# Global singleton instance
pool_manager = ConnectionPoolManager()
