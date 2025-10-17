#!/usr/bin/env python3
"""
Test user update and delete operations (standalone)
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
from app.data.database import get_db_session, async_session
from app.data.models import User
from sqlalchemy import select, update, delete
import pytest

@pytest.mark.asyncio
@pytest.mark.skip(reason="Event loop conflict with SQLAlchemy async sessions when run with other async tests")
async def test_user_operations():
    """Test user update and delete operations."""
    print("🧪 Testing user update and delete operations...")

    db = await get_db_session()
    try:
        # First, let's list existing users to see what we have
        print("\n📋 Current users in database:")
        result = await db.execute(select(User))
        users = result.scalars().all()

        if not users:
            print("   No users found. Please run test_direct.py first to create a test user.")
            return

        for user in users[-3:]:  # Show last 3 users
            print(f"   - {user.preferred_username} (ID: {user.id}) - {user.email}")

        # Pick the first user for testing
        test_user = users[-1]  # Use the most recent user
        print(f"\n🎯 Testing with user: {test_user.preferred_username} (ID: {test_user.id})")

        # Test 1: Update user
        print("\n📝 Testing user update...")
        update_data = {
            "name": f"Updated {test_user.name}",
            "email": f"updated.{test_user.email}"
        }

        stmt = update(User).where(User.id == test_user.id).values(**update_data)
        await db.execute(stmt)
        await db.commit()

        # Refresh the user object
        await db.refresh(test_user)
        print(f"✅ User updated: {test_user.name} - {test_user.email}")

        # Test 2: Delete user (only if it's a test user)
        if "test" in test_user.preferred_username.lower() or "direct" in test_user.preferred_username.lower():
            print("\n🗑️  Testing user delete...")
            try:
                stmt = delete(User).where(User.id == test_user.id)
                result = await db.execute(stmt)
                await db.commit()
                print("✅ User deleted successfully!")
            except Exception as e:
                print(f"❌ Delete failed: {str(e)}")
        else:
            print(f"\n⚠️  Skipping delete test for non-test user: {test_user.preferred_username}")
    finally:
        await db.close()

async def main():
    """Run the user operations test."""
    print("🎯 Testing User CRUD Operations")
    print("="*40)

    await test_user_operations()

    print("\n✅ User operations testing complete!")

if __name__ == "__main__":
    asyncio.run(main())