import redis
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._connect()

    def _connect(self):
        """Establish connection to Redis."""
        try:
            self.client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.client.ping()
            logger.info("Connected to Redis successfully")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            self.client = None

    def is_connected(self) -> bool:
        """Check if Redis client is connected."""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            return False

    def set_revoked_token(self, token: str, ttl_seconds: int) -> bool:
        """Add token to revocation blacklist with TTL."""
        if not self.client:
            logger.error("Redis client not available")
            return False

        try:
            # Use token as key, store minimal data or just use as set
            result = self.client.setex(f"mxwhisper:revoked_token:{token}", ttl_seconds, "1")
            return result is True
        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")
            return False

    def is_token_revoked(self, token: str) -> bool:
        """Check if token is in revocation blacklist."""
        if not self.client:
            logger.error("Redis client not available")
            return False

        try:
            result = self.client.exists(f"mxwhisper:revoked_token:{token}")
            return result == 1
        except Exception as e:
            logger.error(f"Failed to check token revocation: {e}")
            return False

    def health_check(self) -> dict:
        """Perform health check on Redis connection."""
        if not self.client:
            return {"status": "disconnected", "error": "Redis client not initialized"}

        try:
            self.client.ping()
            return {"status": "connected"}
        except Exception as e:
            return {"status": "error", "error": str(e)}