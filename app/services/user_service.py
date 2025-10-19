"""
User management services for MxWhisper
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import Role, User, Job, get_db_session
from app.auth import authentik_client

logger = logging.getLogger(__name__)


class UserService:
    @staticmethod
    async def initialize_roles(db: AsyncSession):
        """Create default roles if they don't exist."""
        roles_data = [
            {"name": "admin", "description": "Administrator with full access"},
            {"name": "user", "description": "Regular user"},
        ]

        for role_data in roles_data:
            role = await db.execute(select(Role).where(Role.name == role_data["name"]))
            role = role.scalar_one_or_none()

            if not role:
                role = Role(**role_data)
                db.add(role)

        await db.commit()

    @staticmethod
    async def create_or_update_user(db: AsyncSession, user_info: dict) -> User:
        """Create or update user from Authentik JWT token info."""
        user_id = user_info.get("sub")
        if not user_id:
            return None

        # Check if user exists
        user = await db.get(User, user_id)
        if user:
            # Update user info
            user.email = user_info.get("email", user.email)
            user.name = user_info.get("name", user.name)
            user.preferred_username = user_info.get("preferred_username", user.preferred_username)

            # Check for admin role from Authentik groups
            groups = user_info.get("groups", [])
            if any(group in ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"] for group in groups):
                admin_role = await db.execute(select(Role).where(Role.name == "admin"))
                admin_role = admin_role.scalar_one_or_none()
                if admin_role:
                    user.role_id = admin_role.id
        else:
            # Create new user
            # Check for admin groups
            groups = user_info.get("groups", [])
            role_name = "admin" if any(group in ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"] for group in groups) else "user"

            role = await db.execute(select(Role).where(Role.name == role_name))
            role = role.scalar_one_or_none()
            role_id = role.id if role else 2  # Default to user role

            user = User(
                id=user_id,
                email=user_info.get("email"),
                name=user_info.get("name"),
                preferred_username=user_info.get("preferred_username"),
                role_id=role_id
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def is_admin(db: AsyncSession, user_id: str) -> bool:
        """Check if user has admin role."""
        user = await db.get(User, user_id)
        if not user:
            return False

        role = await db.get(Role, user.role_id)
        return role and role.name == "admin"

    @staticmethod
    async def user_creation_flow(db: AsyncSession, user_info: dict):
        """Full user creation flow: create user and assign default role."""
        user = await UserService.create_or_update_user(db, user_info)
        if user:
            # Assign default role if not already assigned
            if user.role_id is None:
                default_role = await db.execute(select(Role).where(Role.name == "user"))
                default_role = default_role.scalar_one_or_none()
                user.role_id = default_role.id if default_role else 2  # Default to user role

            await db.commit()
            await db.refresh(user)
        return user

    @staticmethod
    async def store_token_metadata(
        db: AsyncSession,
        user_id: str,
        token_identifier: str,
        expires_at: datetime,
        description: str = ""
    ) -> User:
        """
        Store Authentik token metadata for a user.

        Args:
            db: Database session
            user_id: User ID
            token_identifier: Authentik token identifier
            expires_at: Token expiration datetime
            description: Token description

        Returns:
            Updated User object
        """
        logger.debug("Storing token metadata", extra={
            "user_id": user_id,
            "token_identifier": token_identifier,
            "expires_at": expires_at.isoformat() if expires_at else None
        })

        user = await db.get(User, user_id)
        if not user:
            logger.error("User not found when storing token metadata", extra={
                "user_id": user_id
            })
            raise ValueError(f"User {user_id} not found")

        # Convert timezone-aware datetime to naive UTC datetime for database storage
        # Our database columns are TIMESTAMP WITHOUT TIME ZONE
        expires_at_naive = expires_at.replace(tzinfo=None) if expires_at and expires_at.tzinfo else expires_at

        user.authentik_token_identifier = token_identifier
        user.token_created_at = datetime.now()
        user.token_expires_at = expires_at_naive
        user.token_description = description

        await db.commit()
        await db.refresh(user)

        logger.info("Token metadata stored successfully", extra={
            "user_id": user_id,
            "token_identifier": token_identifier
        })

        return user

    @staticmethod
    async def get_token_metadata(db: AsyncSession, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get token metadata for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dict with token metadata or None if no token
        """
        user = await db.get(User, user_id)
        if not user or not user.authentik_token_identifier:
            return None

        return {
            "identifier": user.authentik_token_identifier,
            "created_at": user.token_created_at,
            "expires_at": user.token_expires_at,
            "description": user.token_description,
            "is_expired": user.token_expires_at < datetime.now() if user.token_expires_at else False
        }

    @staticmethod
    async def clear_token_metadata(db: AsyncSession, user_id: str) -> User:
        """
        Clear token metadata for a user (after revocation).

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Updated User object
        """
        logger.debug("Clearing token metadata", extra={"user_id": user_id})

        user = await db.get(User, user_id)
        if not user:
            logger.error("User not found when clearing token metadata", extra={
                "user_id": user_id
            })
            raise ValueError(f"User {user_id} not found")

        user.authentik_token_identifier = None
        user.token_created_at = None
        user.token_expires_at = None
        user.token_description = None

        await db.commit()
        await db.refresh(user)

        logger.info("Token metadata cleared successfully", extra={
            "user_id": user_id
        })

        return user


async def create_user_in_authentik_and_db(db: AsyncSession, email: str, name: str, preferred_username: str, password: str, role: str = "user") -> User:
    """
    Create a user in both Authentik and our database.

    Args:
        db: Database session
        email: User email
        name: User full name
        preferred_username: Username
        password: User password
        role: User role (default: "user")

    Returns:
        User object from database
    """
    try:
        # 1. Create user in Authentik first
        logger.info("Creating user in Authentik", extra={
            "username": preferred_username,
            "email": email
        })
        
        # Group UUIDs from Authentik (users.mxwhisper: 5ee7c307-198e-4e81-91fe-eb3d9046ab4f, admin.mxwhisper: e8650887-46ed-4b26-9e25-a50679aa768d)
        group_uuids = {
            "users": "5ee7c307-198e-4e81-91fe-eb3d9046ab4f",
            "admin.mxwhisper": "e8650887-46ed-4b26-9e25-a50679aa768d"
        }
        
        groups = [group_uuids["users"]] if role == "user" else [group_uuids["users"], group_uuids["admin.mxwhisper"]]
        
        authentik_user_data = {
            "username": preferred_username,
            "email": email,
            "name": name,
            "password": password,
            "groups": groups
        }
        authentik_user = await authentik_client.create_user(authentik_user_data)
        logger.info("Authentik user created successfully", extra={
            "username": authentik_user['username'],
            "authentik_id": authentik_user['pk'],
            "email": authentik_user['email']
        })

        # 2. Create user in our database
        # Map Authentik user data to our database format
        db_user_data = {
            "sub": str(authentik_user["pk"]),  # Use Authentik user ID
            "email": authentik_user["email"],
            "name": authentik_user["name"],
            "preferred_username": authentik_user["username"],
            "groups": authentik_user_data["groups"]
        }

        logger.debug("Creating user in database", extra={
            "username": db_user_data['preferred_username'],
            "authentik_id": db_user_data['sub']
        })
        database_user = await UserService.create_or_update_user(db, db_user_data)
        logger.info("Database user created successfully", extra={
            "username": database_user.preferred_username,
            "user_id": database_user.id,
            "role": database_user.role.name if database_user.role else None
        })

        logger.info("User creation completed successfully", extra={
            "username": preferred_username,
            "user_id": database_user.id,
            "authentik_id": authentik_user['pk']
        })
        return database_user

    except Exception as e:
        logger.error("Error creating user", extra={
            "username": preferred_username,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise


async def update_user(db: AsyncSession, user_id: str, user_data: dict) -> User:
    """
    Update user information in both Authentik and database.

    Args:
        db: Database session
        user_id: User ID to update
        user_data: Dict containing fields to update

    Returns:
        Updated User object
    """
    # Get current user
    user = await db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Update database user
    if "email" in user_data:
        user.email = user_data["email"]
    if "name" in user_data:
        user.name = user_data["name"]
    if "preferred_username" in user_data:
        user.preferred_username = user_data["preferred_username"]

    # Update role if specified
    if "role" in user_data:
        role_name = user_data["role"]
        role = await db.execute(select(Role).where(Role.name == role_name))
        role = role.scalar_one_or_none()
        if role:
            user.role_id = role.id

    await db.commit()
    await db.refresh(user)

    # TODO: Update Authentik user if needed
    # This would require additional API calls to Authentik

    return user


async def delete_user(db: AsyncSession, user_id: str) -> bool:
    """
    Delete user from both Authentik and database.

    Args:
        db: Database session
        user_id: User ID to delete

    Returns:
        True if successful
    """
    # Get user from database
    user = await db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Delete from database
    await db.delete(user)
    await db.commit()

    # TODO: Delete from Authentik if needed
    # This would require API calls to Authentik

    return True