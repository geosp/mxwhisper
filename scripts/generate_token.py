#!/usr/bin/env python3
"""
Generate JWT token for existing user
"""
import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.data import async_session, User
from app.auth.jwt import create_access_token

async def generate_token_for_user(username: str):
    """Generate a JWT token for an existing user."""
    async with async_session() as db:
        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found")
            return None

        # Generate token data
        token_data = {
            'sub': str(user.id),
            'preferred_username': user.preferred_username,
            'email': user.email,
            'name': user.name,
            'groups': ['users.mxwhisper']  # Default group
        }

        # Generate non-expiring token
        token = create_access_token(token_data, never_expire=True)

        print("✅ Token generated for user:")
        print(f"   Username: {user.preferred_username}")
        print(f"   Email: {user.email}")
        print(f"   User ID: {user.id}")
        print()
        print("🔑 JWT Token:")
        print("=" * 80)
        print(token)
        print("=" * 80)

        return token

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_token.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    asyncio.run(generate_token_for_user(username))