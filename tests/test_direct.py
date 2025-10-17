#!/usr/bin/env python3
"""
Direct test of the user creation function with Authentik integration
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the app directory to Python path
sys.path.insert(0, '/home/geo/develop/mxwhisper')

# Import only what we need, avoiding the workflow imports
from app.data import async_session
from app.auth import authentik_client
from sqlalchemy import select
import pytest

async def create_user_in_authentik_and_db(db, email: str, name: str, preferred_username: str, password: str, role: str):
    """
    Create a user in both Authentik and our database.
    (Standalone version to avoid import issues)
    """
    from app.data.models import Role, User

    try:
        # 1. Create user in Authentik first
        print(f"📝 Creating user in Authentik: {preferred_username}")
        authentik_user_data = {
            "username": preferred_username,
            "email": email,
            "name": name,
            "password": password,
            "groups": ["users"] if role == "user" else ["users", "admin.mxwhisper"]
        }
        authentik_user = await authentik_client.create_user(authentik_user_data)
        print(f"✅ Authentik user created: {authentik_user['username']} (ID: {authentik_user['pk']})")

        # 2. Create user in our database
        # Map Authentik user data to our database format
        db_user_data = {
            "sub": str(authentik_user["pk"]),  # Use Authentik user ID
            "email": authentik_user["email"],
            "name": authentik_user["name"],
            "preferred_username": authentik_user["username"],
            "groups": authentik_user_data["groups"]
        }

        print(f"💾 Creating user in database: {db_user_data['preferred_username']}")

        # Create or update user (copied from JobService.create_or_update_user)
        user_id = db_user_data.get("sub")
        if not user_id:
            raise ValueError("User ID (sub) is required")

        # Check if user exists
        user = await db.get(User, user_id)
        if user:
            # Update user info
            user.email = db_user_data.get("email", user.email)
            user.name = db_user_data.get("name", user.name)
            user.preferred_username = db_user_data.get("preferred_username", user.preferred_username)

            # Check for admin role from Authentik groups
            groups = db_user_data.get("groups", [])
            if any(group in ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"] for group in groups):
                # Assign admin role
                admin_role = await db.execute(select(Role).where(Role.name == "admin"))
                admin_role = admin_role.scalar_one_or_none()
                user.role_id = admin_role.id if admin_role else 1
            else:
                # Assign default user role
                user_role = await db.execute(select(Role).where(Role.name == "user"))
                user_role = user_role.scalar_one_or_none()
                user.role_id = user_role.id if user_role else 2
        else:
            # Create new user
            user = User(
                id=user_id,
                email=db_user_data.get("email"),
                name=db_user_data.get("name"),
                preferred_username=db_user_data.get("preferred_username")
            )

            # Assign role based on groups
            groups = db_user_data.get("groups", [])
            if any(group in ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"] for group in groups):
                # Assign admin role
                admin_role = await db.execute(select(Role).where(Role.name == "admin"))
                admin_role = admin_role.scalar_one_or_none()
                user.role_id = admin_role.id if admin_role else 1
            else:
                # Assign default user role
                user_role = await db.execute(select(Role).where(Role.name == "user"))
                user_role = user_role.scalar_one_or_none()
                user.role_id = user_role.id if user_role else 2

            db.add(user)

        await db.commit()
        
        # Refresh user with role relationship loaded
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(User).options(selectinload(User.role)).where(User.id == user.id)
        )
        user = result.scalar_one()

        print(f"✅ Database user created: {user.preferred_username} (ID: {user.id})")
        print("🎉 User created successfully in both Authentik and database!")
        return user

    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_user_creation():
    """Test the user creation function directly."""
    print("🧪 Testing user creation function directly...")

    # Generate unique username using timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_username = f"directtest_{timestamp}"

    # Test user data
    test_user = {
        "email": f"{unique_username}@example.com",
        "name": "Direct Test User",
        "preferred_username": unique_username,
        "password": "testpassword123",
        "role": "user"
    }

    print(f"📤 Creating user: {test_user['preferred_username']}")

    try:
        # Create database session
        async with async_session() as db:
            # Call the function directly
            user = await create_user_in_authentik_and_db(
                db=db,
                email=test_user["email"],
                name=test_user["name"],
                preferred_username=test_user["preferred_username"],
                password=test_user["password"],
                role=test_user["role"]
            )

            print("✅ User created successfully!")
            print(f"   User ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Username: {user.preferred_username}")
            print(f"   Role: {user.role.name if user.role else 'None'}")
            print(f"   Created: {user.created_at}")

    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        import traceback
        traceback.print_exc()

async def main():
    """Run the direct test."""
    print("🎯 Direct User Creation Test with Authentik Integration")
    print("="*55)

    # Check environment
    print("🔧 Environment check:")
    print(f"   Authentik API URL: {os.getenv('AUTHENTIK_API_URL', 'Not set')}")
    print(f"   Authentik Admin Token: {'Set' if os.getenv('AUTHENTIK_ADMIN_TOKEN') else 'Not set'}")

    await test_user_creation()

    print("\n✅ Direct testing complete!")

if __name__ == "__main__":
    asyncio.run(main())