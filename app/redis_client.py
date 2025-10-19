"""
Redis client for token blacklist operations.
"""
import json
import logging
from typing import Optional, Dict, Any
import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for token blacklist operations."""

    def __init__(self):
        self.client = redis.from_url(settings.redis_url, db=settings.redis_token_db)
        logger.info("Redis client initialized", extra={
            "redis_url": settings.redis_url.replace(settings.redis_url.split('@')[0], '***') if '@' in settings.redis_url else settings.redis_url,
            "db": settings.redis_token_db
        })

    async def set_revoked_token(self, jti: str, metadata: dict, ttl_seconds: int = None) -> bool:
        """Set token as revoked with metadata."""
        if ttl_seconds is None:
            ttl_seconds = settings.redis_token_ttl

        try:
            key = f"mxwhisper:revoked_tokens:{jti}"
            await self.client.setex(key, ttl_seconds, json.dumps(metadata))

            logger.info("Token marked as revoked", extra={
                "jti": jti,
                "reason": metadata.get("reason"),
                "user_id": metadata.get("user_id"),
                "ttl_seconds": ttl_seconds
            })
            return True
        except Exception as e:
            logger.error("Failed to revoke token in Redis", extra={
                "jti": jti,
                "error": str(e)
            })
            return False

    async def is_token_revoked(self, jti: str) -> bool:
        """Check if token is revoked."""
        try:
            key = f"mxwhisper:revoked_tokens:{jti}"
            exists = await self.client.exists(key)
            return exists
        except Exception as e:
            logger.error("Failed to check token revocation", extra={
                "jti": jti,
                "error": str(e)
            })
            # Fail open - allow token if Redis is down
            return False

    async def get_revoked_token_metadata(self, jti: str) -> Optional[Dict[str, Any]]:
        """Get revocation metadata for a token."""
        try:
            key = f"mxwhisper:revoked_tokens:{jti}"
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error("Failed to get token revocation metadata", extra={
                "jti": jti,
                "error": str(e)
            })
            return None

    async def revoke_user_tokens(self, user_id: str, reason: str = "user_logout") -> int:
        """Revoke all tokens for a user (requires tracking user->tokens mapping)."""
        # TODO: Implement if needed - would require additional Redis structure
        # to track which JTIs belong to which users
        logger.warning("Bulk user token revocation not implemented", extra={
            "user_id": user_id,
            "reason": reason
        })
        return 0

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error("Redis health check failed", extra={
                "error": str(e)
            })
            return False


# Global Redis client instance
redis_client = RedisClient()