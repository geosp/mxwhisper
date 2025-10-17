"""
Permission checking and authorization logic for MxWhisper
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def extract_user_info_from_token(token_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user information from JWT token payload.

    Args:
        token_payload: JWT token payload from Authentik

    Returns:
        Dict with user information
    """
    return {
        "sub": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name"),
        "preferred_username": token_payload.get("preferred_username"),
        "groups": token_payload.get("groups", [])
    }


def has_admin_group(user_info: Dict[str, Any]) -> bool:
    """
    Check if user has admin privileges based on groups.

    Args:
        user_info: User information dict

    Returns:
        True if user has admin privileges
    """
    groups = user_info.get("groups", [])
    admin_groups = ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"]

    has_admin = any(group in admin_groups for group in groups)
    logger.debug("Admin group check", extra={
        "username": user_info.get("preferred_username"),
        "groups": groups,
        "has_admin": has_admin
    })

    return has_admin


def get_user_role(user_info: Dict[str, Any]) -> str:
    """
    Determine user role based on group membership.

    Args:
        user_info: User information dict

    Returns:
        Role name ('admin' or 'user')
    """
    if has_admin_group(user_info):
        return "admin"
    return "user"


def can_access_admin_endpoints(user_info: Dict[str, Any]) -> bool:
    """
    Check if user can access admin-only endpoints.

    Args:
        user_info: User information dict

    Returns:
        True if user can access admin endpoints
    """
    return has_admin_group(user_info)


def can_access_user_jobs(user_info: Dict[str, Any], job_user_id: Optional[str]) -> bool:
    """
    Check if user can access specific job based on ownership or admin status.

    Args:
        user_info: User information dict
        job_user_id: User ID associated with the job

    Returns:
        True if user can access the job
    """
    user_id = user_info.get("sub")

    # Admin can access all jobs
    if has_admin_group(user_info):
        return True

    # Users can access their own jobs
    return job_user_id == user_id