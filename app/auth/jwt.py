"""
JWT token handling and verification for MxWhisper
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cache for JWKS keys
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_DURATION = timedelta(hours=24)  # Cache JWKS for 24 hours


async def get_jwks() -> Dict[str, Any]:
    """Fetch and cache JWKS from Authentik."""
    global _jwks_cache, _jwks_cache_time

    now = datetime.utcnow()
    if _jwks_cache and _jwks_cache_time and (now - _jwks_cache_time) < JWKS_CACHE_DURATION:
        logger.debug("Using cached JWKS")
        return _jwks_cache

    logger.info("Fetching JWKS from Authentik", extra={
        "jwks_url": settings.authentik_jwks_url
    })

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.authentik_jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.info("JWKS fetched and cached successfully", extra={
                "keys_count": len(_jwks_cache.get("keys", []))
            })
            return _jwks_cache
    except Exception as e:
        logger.error("Failed to fetch JWKS", extra={
            "error": str(e),
            "error_type": type(e).__name__
        }, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch JWKS: {str(e)}")


def get_public_key(token: str) -> str:
    """Extract public key from JWKS based on token's 'kid' header."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            logger.warning("Token missing 'kid' header")
            raise HTTPException(status_code=401, detail="Token missing 'kid' header")

        jwks = _jwks_cache
        if not jwks:
            logger.warning("JWKS not available for token verification")
            raise HTTPException(status_code=401, detail="JWKS not available")

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                logger.debug("Public key found for token", extra={"kid": kid})
                return key

        logger.warning("Public key not found for token", extra={"kid": kid})
        raise HTTPException(status_code=401, detail="Public key not found for token")
    except JWTError as e:
        logger.error("Invalid token format during key extraction", extra={
            "error": str(e)
        })
        raise HTTPException(status_code=401, detail="Invalid token format")


async def verify_authentik_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token issued by Authentik."""
    token = credentials.credentials
    logger.debug("Verifying Authentik token")

    # Get JWKS
    await get_jwks()

    # Get public key
    public_key = get_public_key(token)

    try:
        # Decode and verify token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],  # Authentik typically uses RS256
            audience=settings.authentik_expected_audience,
            issuer=settings.authentik_expected_issuer
        )

        # Check if token is expired (skip for non-expiring tokens)
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            logger.warning("Token expired", extra={
                "exp": exp,
                "current_time": datetime.utcnow().timestamp()
            })
            raise HTTPException(status_code=401, detail="Token expired")
        elif exp:
            logger.debug("Token has expiration", extra={"exp": exp})
        else:
            logger.info("Non-expiring token verified", extra={
                "sub": payload.get("sub"),
                "username": payload.get("preferred_username")
            })

        logger.info("Token verified successfully", extra={
            "sub": payload.get("sub"),
            "username": payload.get("preferred_username"),
            "exp": exp
        })
        return payload

    except JWTError as e:
        logger.warning("Token validation failed", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


async def verify_legacy_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token using legacy HS256 method (for testing only)."""
    token = credentials.credentials

    try:
        SECRET_KEY = "your-secret-key-here"  # Should match create_access_token
        ALGORITHM = "HS256"

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            logger.warning("Token expired", extra={
                "exp": exp,
                "current_time": datetime.utcnow().timestamp()
            })
            raise HTTPException(status_code=401, detail="Token expired")

        logger.info("Legacy token verified successfully", extra={
            "sub": payload.get("sub"),
            "username": payload.get("preferred_username"),
            "exp": exp
        })
        return payload

    except JWTError as e:
        logger.warning("Legacy token validation failed", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


# Legacy function for backward compatibility (remove after full Authentik integration)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, never_expire: bool = False):
    """Create a JWT token (for development/testing only)."""
    SECRET_KEY = "your-secret-key-here"  # Should be in settings
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

    to_encode = data.copy()
    if never_expire:
        # Don't set expiration for service accounts
        pass
    elif expires_delta:
        expire = datetime.utcnow() + expires_delta
        to_encode.update({"exp": expire})
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Use legacy JWT verification for testing (switch back to Authentik in production)
verify_token = verify_legacy_token