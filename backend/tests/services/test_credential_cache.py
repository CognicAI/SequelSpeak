import pytest
import base64
from unittest.mock import MagicMock, patch, AsyncMock
from services.credential_cache import CredentialCacheService
from config import settings

class TestCredentialCache:
    @pytest.fixture
    def cache_service(self):
        with patch("services.credential_cache.from_url") as mock_from_url:
            service = CredentialCacheService()
            service.redis_client = AsyncMock()
            return service

    def test_derive_key(self, cache_service):
        key = cache_service._derive_key()
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_encrypt_decrypt(self, cache_service):
        password = "test-password-123"
        encrypted = cache_service._encrypt(password)
        assert encrypted != password
        
        decrypted = cache_service._decrypt(encrypted)
        assert decrypted == password

    @pytest.mark.asyncio
    async def test_store_password(self, cache_service):
        user_id = "user123"
        profile_id = "prof456"
        password = "secret-password"
        
        await cache_service.store_password(user_id, profile_id, password)
        
        expected_key = f"cred_cache:{user_id}:{profile_id}"
        cache_service.redis_client.setex.assert_called_once()
        args, _ = cache_service.redis_client.setex.call_args
        assert args[0] == expected_key
        assert args[1] == 3600 # Default TTL
        
        # Verify it's encrypted
        decrypted = cache_service._decrypt(args[2])
        assert decrypted == password

    @pytest.mark.asyncio
    async def test_get_password_success(self, cache_service):
        user_id = "user123"
        profile_id = "prof456"
        password = "secret-password"
        encrypted = cache_service._encrypt(password)
        
        cache_service.redis_client.get.return_value = encrypted
        
        result = await cache_service.get_password(user_id, profile_id)
        assert result == password
        cache_service.redis_client.get.assert_called_once_with(f"cred_cache:{user_id}:{profile_id}")

    @pytest.mark.asyncio
    async def test_get_password_not_found(self, cache_service):
        cache_service.redis_client.get.return_value = None
        result = await cache_service.get_password("user", "prof")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_password(self, cache_service):
        user_id = "user123"
        profile_id = "prof456"
        
        await cache_service.clear_password(user_id, profile_id)
        cache_service.redis_client.delete.assert_called_once_with(f"cred_cache:{user_id}:{profile_id}")

    @pytest.mark.asyncio
    async def test_ensure_redis_already_exists(self, cache_service):
        existing_client = cache_service.redis_client
        await cache_service._ensure_redis()
        assert cache_service.redis_client == existing_client

    @pytest.mark.asyncio
    async def test_ensure_redis_initialization(self):
        with patch("services.credential_cache.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis
            
            service = CredentialCacheService()
            await service._ensure_redis()
            
            assert service.redis_client == mock_redis
            mock_from_url.assert_called_once()
