import os
import base64
import hashlib
from typing import Optional
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError
import logging

from config import settings

logger = logging.getLogger(__name__)

class CredentialCacheService:
    def __init__(self):
        self.redis_client: Optional[Redis] = None
        self._key: bytes = self._derive_key()
        self._ttl = 3600  # Default 1 hour TTL

    def _derive_key(self) -> bytes:
        """Derive exactly a 32-byte key from the app secret key."""
        secret = settings.secret_key or "default-dev-secret-key-do-not-use"
        return hashlib.sha256(secret.encode()).digest()

    def _encrypt(self, plaintext: str) -> str:
        """Encrypts a string using AES-256-GCM."""
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode('utf-8')

    def _decrypt(self, encrypted: str) -> str:
        """Decrypts an AES-256-GCM encrypted string."""
        raw_data = base64.b64decode(encrypted.encode('utf-8'))
        nonce = raw_data[:12]
        ciphertext = raw_data[12:]
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')

    async def _ensure_redis(self):
        if self.redis_client:
            return
        
        # We reuse the Redis configuration from settings
        password_part = f":{settings.redis_password}@" if settings.redis_password else ""
        protocol = "rediss" if settings.redis_ssl else "redis"
        redis_url = (
            f"{protocol}://{password_part}{settings.redis_host}:"
            f"{settings.redis_port}/{settings.redis_db}"
        )
        self.redis_client = from_url(redis_url, decode_responses=True)

    def _get_key(self, user_id: str, profile_id: str) -> str:
        return f"cred_cache:{user_id}:{profile_id}"

    async def store_password(self, user_id: str, profile_id: str, password: str):
        """Store encrypted password in Redis with TTL."""
        try:
            await self._ensure_redis()
            assert self.redis_client is not None
            encrypted = self._encrypt(password)
            key = self._get_key(user_id, profile_id)
            await self.redis_client.setex(key, self._ttl, encrypted)
            logger.debug(f"Stored password for profile {profile_id} in cache (TTL: {self._ttl}s)")
        except RedisError as exc:
            logger.warning(
                "Credential cache unavailable while storing password (profile_id=%s): %s",
                profile_id,
                exc,
            )

    async def get_password(self, user_id: str, profile_id: str) -> Optional[str]:
        """Retrieve and decrypt password from Redis."""
        try:
            await self._ensure_redis()
            assert self.redis_client is not None
            key = self._get_key(user_id, profile_id)
            encrypted = await self.redis_client.get(key)
            if not encrypted:
                return None
            try:
                return self._decrypt(encrypted)
            except (InvalidTag, Exception) as exc:
                # Covers: InvalidTag (wrong key / SECRET_KEY rotation), corrupted base64,
                # truncated ciphertext, or any other decryption failure.
                logger.warning(
                    "Decryption failed for cached credential (profile_id=%s). "
                    "Evicting bad cache entry so caller can prompt for credentials. "
                    "Cause: %s: %s",
                    profile_id, type(exc).__name__, exc,
                )
                await self.redis_client.delete(key)
                return None
        except RedisError as exc:
            logger.warning(
                "Credential cache unavailable while reading password (profile_id=%s): %s",
                profile_id,
                exc,
            )
            return None

    async def clear_password(self, user_id: str, profile_id: str):
        """Manually clear a password from cache."""
        try:
            await self._ensure_redis()
            assert self.redis_client is not None
            key = self._get_key(user_id, profile_id)
            await self.redis_client.delete(key)
        except RedisError as exc:
            logger.warning(
                "Credential cache unavailable while clearing password (profile_id=%s): %s",
                profile_id,
                exc,
            )

credential_cache = CredentialCacheService()
