#!/usr/bin/env python3
"""
Admin User Creation Script

This script creates the admin.mxwhisper user in the database.
Run this after database migrations have been applied.

Usage:
    uv run python scripts/create_admin_user.py

Or make it executable and run directly:
    chmod +x scripts/create_admin_user.py
    ./scripts/create_admin_user.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path so we can import app modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.data.models import User, Role
from app.services import JobService

# Load environment variables
load_dotenv()

async def create_admin_user():
    """Create the admin.mxwhisper user if it doesn't exist."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment variables")
        print("   Make sure your .env file exists and contains DATABASE_URL")
        return False

    print("🔧 Connecting to database...")
    try:
        engine = create_async_engine(database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Ensure roles exist
            print("📋 Ensuring roles are initialized...")
            await JobService.initialize_roles(session)

            # Check if admin user already exists
            admin_user_id = '550e8400-e29b-41d4-a716-446655440000'  # UUID format for admin.mxwhisper
            existing_user = await session.get(User, admin_user_id)

            if existing_user:
                print(f"✅ Admin user already exists: {existing_user.preferred_username}")
                print(f"   ID: {existing_user.id}")
                print(f"   Email: {existing_user.email}")
                print(f"   Role: {'admin' if existing_user.role_id == 1 else 'user'}")
                return True

            # Get admin role
            result = await session.execute(select(Role).where(Role.name == 'admin'))
            admin_role = result.scalar_one_or_none()

            if not admin_role:
                print("❌ ERROR: Admin role not found. Run database migrations first.")
                return False

            # Create admin user
            print("👤 Creating admin.mxwhisper user...")
            admin_user = User(
                id=admin_user_id,
                email='admin@mxwhisper.com',
                name='MxWhisper Admin',
                preferred_username='admin.mxwhisper',
                role_id=admin_role.id
            )

            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

            print("✅ Admin user created successfully!")
            print(f"   ID: {admin_user.id}")
            print(f"   Username: {admin_user.preferred_username}")
            print(f"   Email: {admin_user.email}")
            print(f"   Role: admin")
            print()
            print("🔐 Next steps:")
            print("   1. Set up Authentik with admin.mxwhisper user")
            print("   2. Add admin.mxwhisper to the admin.mxwhisper group")
            print("   3. Test admin endpoints with JWT tokens")
            return True

    except Exception as e:
        print(f"❌ ERROR: Failed to create admin user: {e}")
        return False

async def main():
    """Main entry point."""
    print("🚀 MxWhisper Admin User Creation")
    print("=" * 40)

    success = await create_admin_user()

    if success:
        print("\n✅ Admin user setup complete!")
        return 0
    else:
        print("\n❌ Admin user setup failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)