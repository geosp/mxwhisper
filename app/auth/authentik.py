"""
Authentik API client for admin operations.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import authentik_client as authentik_sdk
from authentik_client.api import CoreApi
from authentik_client.models import UserPasswordSetRequest, UserRequest
from authentik_client.rest import ApiException

from app.config import settings

logger = logging.getLogger(__name__)


class AuthentikAPIClient:
    """Client for Authentik API operations using the official SDK."""

    def __init__(self):
        self.configuration = authentik_sdk.Configuration(
            host=settings.authentik_api_url.rstrip('/'),
            access_token=settings.authentik_admin_token
        )
        logger.debug("Authentik API client initialized", extra={
            "base_url": self.configuration.host
        })

    def _create_user_sync(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous implementation of create_user for SDK compatibility."""
        logger.info("Creating user in Authentik", extra={
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "groups": user_data.get("groups", [])
        })

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # Resolve group names to UUIDs if needed
                group_uuids = []
                if "groups" in user_data:
                    for group_identifier in user_data["groups"]:
                        # Check if it's already a UUID (contains hyphens)
                        if "-" in str(group_identifier):
                            group_uuids.append(group_identifier)
                        else:
                            # Look up group by name
                            group_uuid = self._get_group_id_by_name_sync(group_identifier)
                            if group_uuid:
                                group_uuids.append(group_uuid)

                # Create user request
                user_request = UserRequest(
                    username=user_data["username"],
                    email=user_data["email"],
                    name=user_data.get("name", ""),
                    is_active=True,
                    groups=group_uuids
                )

                # Create the user
                created_user = core_api.core_users_create(user_request)

                # Convert to dict for compatibility with existing code
                result = {
                    "pk": created_user.pk,
                    "username": created_user.username,
                    "email": created_user.email,
                    "name": created_user.name,
                    "is_active": created_user.is_active,
                    "groups": (
                        created_user.groups
                        if hasattr(created_user, "groups")
                        else group_uuids
                    ),
                }

                logger.info("User created successfully in Authentik", extra={
                    "username": result.get("username"),
                    "user_id": result.get("pk"),
                    "email": result.get("email")
                })

                # Set password if provided
                if "password" in user_data:
                    try:
                        password_request = UserPasswordSetRequest(
                            password=user_data["password"]
                        )
                        core_api.core_users_set_password_create(
                            id=created_user.pk,
                            user_password_set_request=password_request
                        )
                        logger.debug("Password set for user", extra={
                            "user_id": created_user.pk
                        })
                    except ApiException as e:
                        logger.warning("Failed to set password for user", extra={
                            "user_id": created_user.pk,
                            "error": str(e)
                        })

                return result

        except ApiException as e:
            logger.error("Failed to create user in Authentik", extra={
                "username": user_data.get("username"),
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            }, exc_info=True)
            raise

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a user in Authentik.

        Args:
            user_data: Dict containing:
                - username: str
                - email: str
                - name: str (optional)
                - password: str (optional)
                - groups: List[str] (optional, group names or UUIDs)

        Returns:
            Dict with created user data from Authentik
        """
        # Run synchronous SDK call in thread pool to avoid blocking
        return await asyncio.to_thread(self._create_user_sync, user_data)

    def _get_group_id_by_name_sync(self, group_name: str) -> Optional[str]:
        """Synchronous implementation of get group UUID by name."""
        logger.debug("Looking up group ID by name", extra={"group_name": group_name})

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # List groups filtered by name
                groups_response = core_api.core_groups_list(name=group_name)

                if groups_response.results and len(groups_response.results) > 0:
                    group_uuid = groups_response.results[0].pk
                    logger.debug("Group found", extra={
                        "group_name": group_name,
                        "group_id": group_uuid
                    })
                    return group_uuid

                logger.debug("Group not found", extra={"group_name": group_name})
                return None

        except ApiException as e:
            logger.error("Failed to look up group", extra={
                "group_name": group_name,
                "error": str(e)
            }, exc_info=True)
            return None

    async def _get_group_id_by_name(self, group_name: str) -> Optional[str]:
        """Get group UUID by name."""
        return await asyncio.to_thread(self._get_group_id_by_name_sync, group_name)

    def _add_user_to_group_sync(self, user_id: str, group_name: str) -> bool:
        """Synchronous implementation of add user to group."""
        logger.info("Adding user to group", extra={
            "user_id": user_id,
            "group_name": group_name
        })

        try:
            group_uuid = self._get_group_id_by_name_sync(group_name)
            if not group_uuid:
                logger.warning("Cannot add user to group - group not found", extra={
                    "user_id": user_id,
                    "group_name": group_name
                })
                return False

            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # Add user to group
                from authentik_client.models import UserAccountRequest
                user_account_request = UserAccountRequest(pk=int(user_id))
                core_api.core_groups_add_user_create(
                    group_uuid=group_uuid,
                    user_account_request=user_account_request
                )

                logger.info("User added to group successfully", extra={
                    "user_id": user_id,
                    "group_name": group_name,
                    "group_id": group_uuid
                })
                return True

        except ApiException as e:
            logger.warning("Failed to add user to group", extra={
                "user_id": user_id,
                "group_name": group_name,
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            }, exc_info=True)
            return False

    async def add_user_to_group(self, user_id: str, group_name: str) -> bool:
        """
        Add a user to a group.

        Args:
            user_id: Authentik user ID (UUID or integer)
            group_name: Name of the group

        Returns:
            True if successful
        """
        return await asyncio.to_thread(self._add_user_to_group_sync, user_id, group_name)

    def _get_user_sync(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous implementation of get user."""
        logger.debug("Getting user by ID", extra={"user_id": user_id})

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                user = core_api.core_users_retrieve(id=int(user_id))

                # Convert to dict for compatibility
                result = {
                    "pk": user.pk,
                    "username": user.username,
                    "email": user.email,
                    "name": user.name,
                    "is_active": user.is_active,
                    "groups": user.groups if hasattr(user, 'groups') else []
                }

                logger.debug("User found", extra={
                    "user_id": user_id,
                    "username": result.get("username")
                })
                return result

        except ApiException as e:
            logger.debug("User not found", extra={
                "user_id": user_id,
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            })
            return None

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return await asyncio.to_thread(self._get_user_sync, user_id)


# Global client instance
# Note: Variable name must be different from the imported module
authentik_api_client = AuthentikAPIClient()
