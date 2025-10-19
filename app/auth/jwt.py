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


async def verify_authentik_api_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify Authentik API token by calling Authentik's user info endpoint.

    Authentik API tokens are opaque tokens (not JWTs) that need to be verified
    by calling Authentik's API.
    """
    if not settings.authentik_server_url:
        logger.warning("Authentik server URL not configured")
        return None

    try:
        # Call Authentik's user info endpoint with the token
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.authentik_server_url}/application/o/userinfo/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )

            if response.status_code == 200:
                user_info = response.json()
                logger.info("Authentik API token verified successfully", extra={
                    "sub": user_info.get("sub"),
                    "username": user_info.get("preferred_username")
                })
                return user_info
            else:
                logger.debug("Authentik API token verification failed", extra={
                    "status_code": response.status_code
                })
                return None

    except Exception as e:
        logger.debug("Failed to verify Authentik API token", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        return None


async def verify_authentik_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token or API token issued by Authentik."""
    token = credentials.credentials
    logger.debug("Verifying Authentik token")

    # First, try to verify as an Authentik API token (opaque token)
    # These are ~60 character tokens without JWT structure
    if len(token) < 100 and '.' not in token:
        logger.debug("Token appears to be an Authentik API token, verifying via API")
        user_info = await verify_authentik_api_token(token)
        if user_info:
            return user_info
        else:
            # API token verification failed
            logger.warning("Authentik API token verification failed")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Try to verify as a JWT token
    try:
        # Get JWKS
        await get_jwks()

        # Get public key
        public_key = get_public_key(token)

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

        logger.info("JWT token verified successfully", extra={
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


def create_service_account_token(user_data: dict, expires_days: int = 365) -> str:
    """
    Create a service account JWT token for API access.

    These are self-signed JWTs that don't require OAuth2 web login.
    They're meant for programmatic API access (scripts, services, etc.).

    Args:
        user_data: User information dict with keys: sub, email, name, preferred_username, groups
        expires_days: Days until token expires (default: 365)

    Returns:
        JWT token string
    """
    from app.services.token_service import TokenService

    token_service = TokenService()

    # Prepare token data
    token_data = {
        "sub": user_data.get("sub"),
        "username": user_data.get("preferred_username", user_data.get("username")),
        "roles": user_data.get("groups", [])
    }

    # Create token with JTI using TokenService
    expires_delta = timedelta(days=expires_days)
    token = token_service.create_access_token(token_data, expires_delta)

    logger.info("Service account token created", extra={
        "sub": user_data.get("sub"),
        "username": user_data.get("preferred_username"),
        "expires_days": expires_days
    })

    return token


async def verify_service_account_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a service account JWT token.

    These are self-signed JWTs for API access without OAuth2.
    """
    from app.services.token_service import TokenService

    token_service = TokenService()

    # Use TokenService to verify token (includes Redis blacklist check)
    token_data = token_service.verify_token(token)

    if not token_data:
        logger.debug("Service account token validation failed or token revoked")
        return None

    # Convert TokenData back to dict format for compatibility
    payload = {
        "sub": token_data.user_id,
        "username": token_data.username,
        "roles": token_data.roles,
        "exp": token_data.exp.timestamp(),
        "iat": token_data.iat.timestamp(),
        "jti": token_data.jti,
        "token_type": "service_account"
    }

    logger.info("Service account token verified successfully", extra={
        "sub": payload.get("sub"),
        "username": payload.get("username")
    })

    return payload


async def verify_token_with_fallback(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Verify token with multiple fallback methods:
    1. Service account JWT (self-signed for API access)
    2. Authentik API token (opaque token)
    3. Authentik JWT token (OAuth2/OIDC)
    """
    token = credentials.credentials
    logger.debug("Verifying token with fallback methods")

    # Try service account JWT first (most common for API access)
    if '.' in token:  # JWTs have dots
        service_account_payload = await verify_service_account_token(token)
        if service_account_payload:
            return service_account_payload

    # Try Authentik API token (opaque token ~60 chars)
    if len(token) < 100 and '.' not in token:
        logger.debug("Token appears to be an Authentik API token, verifying via API")
        user_info = await verify_authentik_api_token(token)
        if user_info:
            return user_info
        else:
            # API token verification failed
            logger.warning("Authentik API token verification failed")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Try Authentik JWT token (OAuth2/OIDC)
    try:
        # Get JWKS
        await get_jwks()

        # Get public key
        public_key = get_public_key(token)

        # Decode and verify token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],  # Authentik typically uses RS256
            audience=settings.authentik_expected_audience,
            issuer=settings.authentik_expected_issuer
        )

        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            logger.warning("Authentik JWT token expired", extra={
                "exp": exp,
                "current_time": datetime.utcnow().timestamp()
            })
            raise HTTPException(status_code=401, detail="Token expired")

        logger.info("Authentik JWT token verified successfully", extra={
            "sub": payload.get("sub"),
            "username": payload.get("preferred_username"),
            "exp": exp
        })
        return payload

    except JWTError as e:
        logger.warning("All token validation methods failed", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


# Set default token verification to use fallback method (tries all token types)
verify_token = verify_token_with_fallback