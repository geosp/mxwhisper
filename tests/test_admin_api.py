#!/usr/bin/env python3
"""
Test the new admin user creation endpoint
"""

import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest
from jose import jwt

from app.config import settings

# Mock JWT secret for testing (same as in auth.py)
JWT_SECRET = "your-secret-key-here"
JWT_ALGORITHM = "HS256"

def create_admin_jwt() -> str:
    """Create a mock JWT token for admin user for testing.

    Note: Since we removed legacy token creation, this creates a token
    using the same format that Authentik would issue. For real Authentik tokens,
    use the actual Authentik server or mock the verification instead.
    """
    from jose import jwt
    from datetime import timedelta, datetime

    user_data = {
        "sub": "550e8400-e29b-41d4-a716-446655440000",  # UUID format
        "email": "admin@mxwhisper.com",
        "name": "MxWhisper Admin",
        "preferred_username": "admin.mxwhisper",
        "groups": ["admin.mxwhisper", "users"],
        "exp": datetime.utcnow() + timedelta(hours=1)
    }

    # Create a test token using HS256 for testing purposes
    # In production, Authentik uses RS256 with proper key pairs
    return jwt.encode(user_data, JWT_SECRET, algorithm=JWT_ALGORITHM)

@pytest.mark.asyncio
async def test_create_user():
    """Test the POST /admin/users endpoint."""
    print("🧪 Testing POST /admin/users endpoint...")

    # Create admin token
    admin_token = create_admin_jwt()
    print(f"📝 Created admin token for: {jwt.decode(admin_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])['preferred_username']}")

    # Test user data
    test_user = {
        "email": "testuser@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "password": "testpassword123",
        "role": "user"
    }

    # Make request
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://localhost:3001/admin/users",
                json=test_user,
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30.0
            )

            print(f"📡 Response status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print("✅ User created successfully!")
                print(f"   User ID: {result['id']}")
                print(f"   Email: {result['email']}")
                print(f"   Username: {result['preferred_username']}")
                print(f"   Role: {result['role']}")
            else:
                print(f"❌ Request failed: {response.text}")

        except Exception as e:
            print(f"❌ Request error: {str(e)}")

@pytest.mark.asyncio
async def test_get_users():
    """Test the GET /admin/users endpoint."""
    print("\n📋 Testing GET /admin/users endpoint...")

    # Create admin token
    admin_token = create_admin_jwt()

    # Make request
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "http://localhost:3001/admin/users",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=10.0
            )

            print(f"📡 Response status: {response.status_code}")
            if response.status_code == 200:
                users = response.json()
                print(f"✅ Retrieved {len(users)} users")
                for user in users[:3]:  # Show first 3 users
                    print(f"   - {user['preferred_username']} ({user['email']}) - {user['role']}")
            else:
                print(f"❌ Request failed: {response.text}")

        except Exception as e:
            print(f"❌ Request error: {str(e)}")

async def main():
    """Run all tests."""
    print("🎯 Testing Admin User Management API")
    print("="*50)

    await test_get_users()
    await test_create_user()
    await test_get_users()  # Check if user was added

    print("\n✅ Testing complete!")

if __name__ == "__main__":
    asyncio.run(main())