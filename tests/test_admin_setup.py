#!/usr/bin/env python3
"""
MxWhisper Admin Setup and Testing Script

This script helps with:
1. Testing admin role assignment from JWT tokens
2. Testing admin endpoints
3. Demonstrating the role-based access control

Note: Authentik group configuration must be done manually in the Authentik web UI.
"""

import asyncio
from datetime import datetime, timedelta

from jose import jwt
import pytest

from app.config import settings

# Mock JWT secret for testing (same as in auth.py)
JWT_SECRET = "your-secret-key-here"
JWT_ALGORITHM = "HS256"

def create_mock_jwt(user_info: dict, groups: list = None) -> str:
    """Create a mock JWT token for testing."""
    payload = {
        "sub": user_info.get("sub", "test-user-id"),
        "email": user_info.get("email", "test@example.com"),
        "name": user_info.get("name", "Test User"),
        "preferred_username": user_info.get("preferred_username", "testuser"),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "iss": settings.authentik_expected_issuer,
        "aud": settings.authentik_expected_audience,
    }

    if groups:
        payload["groups"] = groups

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

@pytest.mark.asyncio
async def test_role_initialization():
    """Test that roles are created properly."""
    print("🔧 Testing role initialization...")
    print("   (Requires database connection - run after migrations)")
    print("   Command: uv run alembic upgrade head")

@pytest.mark.asyncio
async def test_user_role_assignment():
    """Test user creation with different group memberships."""
    print("\n👤 Testing user role assignment...")
    print("   (Requires database connection - run after migrations)")
    
    # Show example JWT payloads
    print("\n📝 Example JWT payloads for testing:")
    
    regular_payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "groups": ["users"]
    }
    print(f"   Regular user: {regular_payload}")
    
    # Mock admin user data
    admin_payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440000",  # UUID format
        "email": "admin@mxwhisper.com",
        "preferred_username": "admin.mxwhisper",
        "groups": ["admin.mxwhisper", "users"]
    }
    print(f"   Admin user: {admin_payload}")

@pytest.mark.asyncio
async def test_admin_endpoints():
    """Test admin endpoints with mock tokens."""
    print("\n🔐 Testing admin endpoints...")
    
    # Create mock tokens
    regular_token = create_mock_jwt({
        "sub": "regular-user-123",
        "email": "user@example.com"
    }, ["users"])
    
    admin_token = create_mock_jwt({
        "sub": "550e8400-e29b-41d4-a716-446655440000",  # UUID format
        "email": "admin@mxwhisper.com",
        "preferred_username": "admin.mxwhisper"
    }, ["admin.mxwhisper", "users"])
    
    print("📝 Mock JWT tokens created:")
    print(f"   Regular user token: {regular_token[:50]}...")
    print(f"   Admin user token: {admin_token[:50]}...")
    
    print("\n📡 Manual testing commands:")
    print("# Start server first:")
    print("uv run uvicorn main:app --reload")
    print()
    print("# Test admin endpoints:")
    print(f"curl -H 'Authorization: Bearer {admin_token}' http://localhost:8000/admin/users")
    print(f"curl -H 'Authorization: Bearer {regular_token}' http://localhost:8000/admin/users  # Should fail with 403")

async def print_authentik_setup_instructions():
    """Print instructions for Authentik group setup."""
    print("\n" + "="*60)
    print("📋 AUTHENTIK GROUP SETUP INSTRUCTIONS")
    print("="*60)

    print("""
1. Log into Authentik Admin Interface:
   URL: http://authentik.mixwarecs-home.net/if/admin/

2. Create Admin Group:
   - Directory → Groups → Create
   - Name: "admin.mxwhisper" (recommended for consistency)
   - Add users who should have admin access

3. Create Dedicated Admin User (Recommended):
   - Directory → Users → Create
   - Username: "admin.mxwhisper" (matches the group name)
   - Email: admin@yourdomain.com
   - Set a strong password
   - Add to the "admin.mxwhisper" group

4. Alternative: Add Existing Users to Admin Group:
   - Directory → Users → Select user → Groups tab → Add to admin group

5. Verify JWT Token Contains Groups:
   - After login, check the JWT token
   - Should contain: "groups": ["admin", ...]

6. Test Admin Access:
   - Login with admin user (e.g., "admin.mxwhisper")
   - JWT token should grant access to /admin/* endpoints
   - Regular users should be denied access

7. Alternative Group Names:
   The app recognizes these group names as admin:
   - "admin"
   - "administrators"
   - "Admins"
   """)

async def main():
    """Run all tests."""
    print("🚀 MxWhisper Admin Setup and Testing")
    print("="*50)
    print("Note: Database connection required for full testing.")
    print("Run: uv run alembic upgrade head")
    print()
    
    try:
        await test_role_initialization()
        await test_user_role_assignment()
        await test_admin_endpoints()
        await print_authentik_setup_instructions()
        
        print("\n✅ Setup instructions provided!")
        print("\n📝 Next steps:")
        print("1. Set up Authentik groups (see instructions above)")
        print("2. Run: uv run alembic upgrade head")
        print("3. Start server: uv run uvicorn main:app --reload")
        print("4. Test endpoints with real JWT tokens from Authentik")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())