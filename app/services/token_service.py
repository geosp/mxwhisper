import uuid
from datetime import datetime, timedelta
from typing import Optional
import logging

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings
from app.data.redis_client import RedisClient
from app.data import get_db_session, User

logger = logging.getLogger(__name__)


class TokenData(BaseModel):
    user_id: str
    username: str
    roles: list[str] = []
    exp: datetime
    iat: datetime
    jti: str
    revocation_counter: int = 0


class TokenService:
    def __init__(self):
        self.redis_client = RedisClient()
        self.secret_key = settings.service_account_jwt_secret
        self.algorithm = settings.service_account_jwt_algorithm
        self.access_token_expire_minutes = 60 * 24 * 365  # 1 year in minutes

    def _get_user_revocation_counter(self, user_id: str) -> int:
        """Get the current revocation counter for a user."""
        import asyncio
        try:
            # Get current event loop or create new one
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, need to handle differently
                    # For now, return 0 and handle this properly later
                    return 0
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run database query
            async def get_counter():
                db = await get_db_session()
                try:
                    user = await db.get(User, user_id)
                    return user.token_revocation_counter if user else 0
                finally:
                    await db.close()

            return loop.run_until_complete(get_counter())
        except Exception as e:
            logger.error(f"Failed to get user revocation counter: {e}")
            return 0

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None, revocation_counter: int = 0) -> str:
        """Create a JWT access token with JTI for revocation support."""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),  # Unique token identifier for revocation
            "revocation_counter": revocation_counter  # Include revocation counter
        })

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify JWT token and check if it's revoked."""
        try:
            # First check if token is revoked
            if self.redis_client.is_token_revoked(token):
                return None

            # Decode and validate token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Extract token data
            token_data = TokenData(
                user_id=payload.get("sub"),
                username=payload.get("username"),
                roles=payload.get("roles", []),
                exp=datetime.fromtimestamp(payload.get("exp")),
                iat=datetime.fromtimestamp(payload.get("iat")),
                jti=payload.get("jti"),
                revocation_counter=payload.get("revocation_counter", 0)
            )

            # Check revocation counter against current user counter
            current_counter = self._get_user_revocation_counter(token_data.user_id)
            if token_data.revocation_counter < current_counter:
                logger.info("Token revoked due to counter mismatch", extra={
                    "user_id": token_data.user_id,
                    "token_counter": token_data.revocation_counter,
                    "current_counter": current_counter
                })
                return None

            return token_data

        except JWTError:
            return None
        except Exception:
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke a JWT token by adding it to the blacklist."""
        try:
            # Manually decode the JWT payload to get expiration time
            import base64
            import json
            
            parts = token.split('.')
            if len(parts) != 3:
                return False
                
            payload_b64 = parts[1]
            # Add padding if needed
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload_str = payload_bytes.decode('utf-8')
            payload = json.loads(payload_str)
            
            exp_timestamp = payload.get("exp")

            if exp_timestamp:
                # Calculate TTL until token naturally expires
                expire_time = datetime.fromtimestamp(exp_timestamp)
                ttl_seconds = int((expire_time - datetime.utcnow()).total_seconds())

                if ttl_seconds > 0:
                    return self.redis_client.set_revoked_token(token, ttl_seconds)

            # If no expiration or already expired, still revoke but with default TTL
            return self.redis_client.set_revoked_token(token, 3600)  # 1 hour default

        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")
            return False

    def revoke_all_user_tokens(self, user_id: str) -> bool:
        """Revoke all tokens for a specific user by incrementing revocation counter."""
        import asyncio
        try:
            # Get current event loop or create new one
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, need to handle differently
                    return False
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run database update
            async def revoke_tokens():
                db = await get_db_session()
                try:
                    user = await db.get(User, user_id)
                    if not user:
                        return False

                    # Increment revocation counter
                    user.token_revocation_counter += 1
                    await db.commit()
                    await db.refresh(user)

                    logger.info("All tokens revoked for user by incrementing counter", extra={
                        "user_id": user_id,
                        "new_counter": user.token_revocation_counter
                    })
                    return True
                finally:
                    await db.close()

            return loop.run_until_complete(revoke_tokens())
        except Exception as e:
            logger.error(f"Failed to revoke all user tokens: {e}")
            return False