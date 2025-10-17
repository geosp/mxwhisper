"""
Authentik API client for admin operations.
"""

import httpx
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class AuthentikAPIClient:
    """Client for Authentik REST API operations."""

    def __init__(self):
        self.base_url = settings.authentik_api_url.rstrip('/')
        self.admin_token = settings.authentik_admin_token
        self.headers = {
            'Authorization': f'Bearer {self.admin_token}',
            'Content-Type': 'application/json'
        }
        logger.debug("Authentik API client initialized", extra={
            "base_url": self.base_url
        })

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a user in Authentik.

        Args:
            user_data: Dict containing:
                - username: str
                - email: str
                - name: str (optional)
                - groups: List[str] (optional)

        Returns:
            Dict with created user data from Authentik
        """
        logger.info("Creating user in Authentik", extra={
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "groups": user_data.get("groups", [])
        })

        url = f"{self.base_url}/core/users/"

        # Prepare user data for Authentik API
        authentik_user_data = {
            "username": user_data["username"],
            "email": user_data["email"],
            "name": user_data.get("name", ""),
            "is_active": True,
            "groups": []
        }

        # Add groups if specified
        if "groups" in user_data:
            # We need to get group IDs from names
            for group_name in user_data["groups"]:
                group_id = await self._get_group_id_by_name(group_name)
                if group_id:
                    authentik_user_data["groups"].append(group_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=authentik_user_data,
                headers=self.headers
            )

            response.raise_for_status()
            created_user = response.json()
            logger.info("User created successfully in Authentik", extra={
                "username": created_user.get("username"),
                "user_id": created_user.get("pk"),
                "email": created_user.get("email")
            })
            return created_user

    async def _get_group_id_by_name(self, group_name: str) -> Optional[int]:
        """Get group ID by name."""
        logger.debug("Looking up group ID by name", extra={"group_name": group_name})

        url = f"{self.base_url}/core/groups/"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                params={"name": group_name}
            )
            response.raise_for_status()
            groups = response.json()["results"]

            if groups:
                group_id = groups[0]["pk"]
                logger.debug("Group found", extra={
                    "group_name": group_name,
                    "group_id": group_id
                })
                return group_id
            logger.debug("Group not found", extra={"group_name": group_name})
            return None

    async def add_user_to_group(self, user_id: str, group_name: str) -> bool:
        """
        Add a user to a group.

        Args:
            user_id: Authentik user ID
            group_name: Name of the group

        Returns:
            True if successful
        """
        logger.info("Adding user to group", extra={
            "user_id": user_id,
            "group_name": group_name
        })

        group_id = await self._get_group_id_by_name(group_name)
        if not group_id:
            logger.warning("Cannot add user to group - group not found", extra={
                "user_id": user_id,
                "group_name": group_name
            })
            return False

        url = f"{self.base_url}/core/users/{user_id}/groups/"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"pk": group_id},
                headers=self.headers
            )
            success = response.status_code == 204
            if success:
                logger.info("User added to group successfully", extra={
                    "user_id": user_id,
                    "group_name": group_name,
                    "group_id": group_id
                })
            else:
                logger.warning("Failed to add user to group", extra={
                    "user_id": user_id,
                    "group_name": group_name,
                    "status_code": response.status_code
                })
            return success

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        logger.debug("Getting user by ID", extra={"user_id": user_id})

        url = f"{self.base_url}/core/users/{user_id}/"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                user_data = response.json()
                logger.debug("User found", extra={
                    "user_id": user_id,
                    "username": user_data.get("username")
                })
                return user_data
            logger.debug("User not found", extra={
                "user_id": user_id,
                "status_code": response.status_code
            })
            return None


# Global client instance
authentik_client = AuthentikAPIClient()