"""
Authentication and authorization layer for MxWhisper
"""
from .jwt import verify_token, verify_authentik_token, create_access_token, security
from .authentik import authentik_api_client as authentik_client, AuthentikAPIClient
from .permissions import (
    extract_user_info_from_token,
    has_admin_group,
    get_user_role,
    can_access_admin_endpoints,
    can_access_user_jobs
)

__all__ = [
    "verify_token",
    "verify_authentik_token",
    "create_access_token",
    "security",
    "authentik_client",  # Aliased from authentik_api_client for backward compatibility
    "AuthentikAPIClient",
    "extract_user_info_from_token",
    "has_admin_group",
    "get_user_role",
    "can_access_admin_endpoints",
    "can_access_user_jobs"
]