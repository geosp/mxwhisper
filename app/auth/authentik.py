"""
Authentik API client for admin operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

import authentik_client as authentik_sdk
from authentik_client.api import CoreApi
from authentik_client.models import (
    UserPasswordSetRequest,
    UserRequest,
    TokenRequest,
    IntentEnum
)
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

    def _get_user_by_username_sync(self, username: str) -> Optional[Dict[str, Any]]:
        """Synchronous implementation of get user by username."""
        logger.debug("Getting user by username", extra={"username": username})

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # List users filtered by username
                users_response = core_api.core_users_list(username=username)

                if users_response.results and len(users_response.results) > 0:
                    user = users_response.results[0]
                    result = {
                        "pk": user.pk,
                        "username": user.username,
                        "email": user.email,
                        "name": user.name,
                        "is_active": user.is_active,
                        "groups": user.groups if hasattr(user, 'groups') else []
                    }
                    logger.debug("User found", extra={
                        "username": username,
                        "user_pk": result.get("pk")
                    })
                    return result

                logger.debug("User not found", extra={"username": username})
                return None

        except ApiException as e:
            logger.error("Failed to look up user by username", extra={
                "username": username,
                "error": str(e)
            }, exc_info=True)
            return None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        return await asyncio.to_thread(self._get_user_by_username_sync, username)

    def _create_token_sync(
        self,
        user_pk: int,
        identifier: str,
        description: str = "",
        expires_days: int = 365
    ) -> Dict[str, Any]:
        """
        Synchronous implementation of create Authentik API token.

        Args:
            user_pk: Authentik user primary key (integer ID)
            identifier: Unique identifier for the token
            description: Human-readable description
            expires_days: Days until token expires (default: 365)

        Returns:
            Dict with token data including:
                - key: The actual token value (shown only once!)
                - identifier: Token identifier
                - expires: Expiration datetime
                - pk: Token primary key
        """
        logger.info("Creating Authentik API token", extra={
            "user_pk": user_pk,
            "identifier": identifier,
            "expires_days": expires_days
        })

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # Calculate expiration date
                expires_at = datetime.now() + timedelta(days=expires_days)

                # Create token request
                token_request = TokenRequest(
                    identifier=identifier,
                    user=user_pk,
                    intent=IntentEnum.API,
                    description=description,
                    expires=expires_at,
                    expiring=True
                )

                # Create the token
                token = core_api.core_tokens_create(token_request)

                # Retrieve the token key (actual secret value)
                # The key is only available through view_key_retrieve and will be logged in Authentik
                token_view = core_api.core_tokens_view_key_retrieve(identifier=identifier)

                # Extract token data
                result = {
                    "key": token_view.key,  # The actual token value - shown only once!
                    "identifier": token.identifier,
                    "expires": token.expires,
                    "pk": token.pk,
                    "description": token.description if hasattr(token, "description") else description
                }

                logger.info("Authentik API token created successfully", extra={
                    "identifier": identifier,
                    "expires": expires_at.isoformat()
                })

                return result

        except ApiException as e:
            logger.error("Failed to create Authentik token", extra={
                "user_pk": user_pk,
                "identifier": identifier,
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            }, exc_info=True)
            raise

    async def create_token(
        self,
        user_pk: int,
        identifier: str,
        description: str = "",
        expires_days: int = 365
    ) -> Dict[str, Any]:
        """
        Create an Authentik API token for a user.

        Args:
            user_pk: Authentik user primary key (integer ID)
            identifier: Unique identifier for the token
            description: Human-readable description
            expires_days: Days until token expires (default: 365)

        Returns:
            Dict with token data including the token key (shown only once!)
        """
        return await asyncio.to_thread(
            self._create_token_sync,
            user_pk,
            identifier,
            description,
            expires_days
        )

    def _revoke_token_sync(self, token_identifier: str) -> bool:
        """
        Synchronous implementation of revoke Authentik token.

        Args:
            token_identifier: The token identifier to revoke

        Returns:
            True if successful
        """
        logger.info("Revoking Authentik token", extra={
            "identifier": token_identifier
        })

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # Delete the token
                core_api.core_tokens_destroy(identifier=token_identifier)

                logger.info("Authentik token revoked successfully", extra={
                    "identifier": token_identifier
                })
                return True

        except ApiException as e:
            logger.error("Failed to revoke Authentik token", extra={
                "identifier": token_identifier,
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            }, exc_info=True)
            return False

    async def revoke_token(self, token_identifier: str) -> bool:
        """
        Revoke an Authentik API token.

        Args:
            token_identifier: The token identifier to revoke

        Returns:
            True if successful
        """
        return await asyncio.to_thread(self._revoke_token_sync, token_identifier)

    def _list_user_tokens_sync(self, username: str) -> List[Dict[str, Any]]:
        """
        Synchronous implementation of list tokens for a user.

        Args:
            username: Authentik username

        Returns:
            List of token dictionaries
        """
        logger.debug("Listing tokens for user", extra={"username": username})

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # List tokens filtered by username
                tokens_response = core_api.core_tokens_list(user__username=username)

                tokens = []
                if tokens_response.results:
                    for token in tokens_response.results:
                        tokens.append({
                            "identifier": token.identifier,
                            "expires": token.expires,
                            "expiring": token.expiring if hasattr(token, 'expiring') else True,
                            "description": token.description if hasattr(token, 'description') else "",
                            "pk": token.pk
                        })

                logger.debug("Found tokens for user", extra={
                    "username": username,
                    "count": len(tokens)
                })

                return tokens

        except ApiException as e:
            logger.error("Failed to list user tokens", extra={
                "username": username,
                "error": str(e)
            }, exc_info=True)
            return []

    async def list_user_tokens(self, username: str) -> List[Dict[str, Any]]:
        """
        List all Authentik API tokens for a user.

        Args:
            username: Authentik username

        Returns:
            List of token dictionaries
        """
        return await asyncio.to_thread(self._list_user_tokens_sync, username)

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user from Authentik.

        Args:
            user_id: Authentik user ID (pk)

        Returns:
            True if deletion was successful, False otherwise
        """
        return await asyncio.to_thread(self._delete_user_sync, user_id)

    def _delete_user_sync(self, user_id: str) -> bool:
        """Synchronous implementation of delete_user for SDK compatibility."""
        logger.info("Deleting user from Authentik", extra={
            "user_id": user_id
        })

        try:
            with authentik_sdk.ApiClient(self.configuration) as api_client:
                core_api = CoreApi(api_client)

                # Delete the user
                core_api.core_users_destroy(id=user_id)

                logger.info("User deleted successfully from Authentik", extra={
                    "user_id": user_id
                })

                return True

        except ApiException as e:
            logger.error("Failed to delete user from Authentik", extra={
                "user_id": user_id,
                "error": str(e),
                "status_code": e.status if hasattr(e, 'status') else None
            }, exc_info=True)
            return False
        except Exception as e:
            logger.error("Unexpected error deleting user from Authentik", extra={
                "user_id": user_id,
                "error": str(e)
            }, exc_info=True)
            return False


# Global client instance
# Note: Variable name must be different from the imported module
authentik_api_client = AuthentikAPIClient()
