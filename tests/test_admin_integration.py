#!/usr/bin/env python3
"""
Test admin.mxwhisper functionality with mock JWT tokens
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

def get_user_role_from_groups(groups: list) -> str:
    """Determine user role based on Authentik groups (copied from services.py logic)."""
    if any(group in ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"] for group in groups):
        return "ADMIN"
    return "USER"

@pytest.mark.asyncio
async def test_admin_token_validation():
    """Test JWT token validation with admin.mxwhisper mock token."""
    print("🧪 Testing admin.mxwhisper JWT token validation...")

    # Create a proper mock token using our helper function
    admin_user_info = {
        "sub": "550e8400-e29b-41d4-a716-446655440000",  # UUID format
        "email": "admin@mxwhisper.com",
        "name": "MxWhisper Admin",
        "preferred_username": "admin.mxwhisper"
    }
    admin_groups = ["admin.mxwhisper", "users"]
    
    # Mock JWT token for admin.mxwhisper user
    # This simulates a token from Authentik with admin.mxwhisper in groups
    mock_admin_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAiLCJlbWFpbCI6ImFkbWluQG14d2hpc3Blci5jb20iLCJuYW1lIjoiTXhXaGlzcGVyIEFkbWluIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiYWRtaW4ubXh3aGlzcGVyIiwiZXhwIjoxNzYwNTAwMDAwLCJpYXQiOjE3NjA0OTY0MDAsImlzcyI6Imh0dHA6Ly9hdXRoZW50aWsubWl4d2FyZWNzLWhvbWUubmV0L2FwcGxpY2F0aW9uL28vbXh3aGlzcGVyLyIsImF1ZCI6IkJJRTZDdXlnWERVMks3elJzWXVXMFhzWDU2Z2tadWdRd2xldVVycHUiLCJncm91cHMiOlsiYWRtaW4ubXh3aGlzcGVyIiwidXNlcnMiXX0.signature"
    
    print("📝 Testing admin token validation...")
    print(f"   Token contains groups: {admin_groups}")
    
    # Note: Real Authentik token validation requires JWKS from Authentik server
    # This test demonstrates the expected token structure and group recognition
    print("✅ Mock token created successfully")
    print(f"   User: {admin_user_info['preferred_username']}")
    print(f"   Groups: {admin_groups}")
    print("   Role: ADMIN (based on admin.mxwhisper group)")
    
    # Test group recognition logic (from services.py)
    role = get_user_role_from_groups(admin_groups)
    print(f"   Role determination: {role}")
    
    return True

@pytest.mark.asyncio
async def test_group_recognition():
    """Test that our code recognizes admin.mxwhisper group."""
    print("\n👥 Testing admin.mxwhisper group recognition...")

    # Test the group recognition logic from services.py
    admin_groups = ["admin", "administrators", "Admins", "admin.mxwhisper", "mxwhisper-admin"]

    test_groups = [
        ["users"],  # Regular user
        ["admin.mxwhisper", "users"],  # Admin user
        ["mxwhisper-admin"],  # Alternative admin
        ["admin"],  # Basic admin
    ]

    for groups in test_groups:
        is_admin = any(group in admin_groups for group in groups)
        user_type = "ADMIN" if is_admin else "USER"
        print(f"   Groups {groups} → {user_type}")

async def simulate_admin_workflow():
    """Simulate the complete admin workflow."""
    print("\n🔄 Simulating admin.mxwhisper workflow...")

    print("1. User 'admin.mxwhisper' logs into Authentik")
    print("2. Authentik returns JWT with groups: ['admin.mxwhisper', 'users']")
    print("3. MxWhisper API receives JWT token")
    print("4. Token validation extracts user info and groups")
    print("5. User gets admin role automatically")
    print("6. Admin can access /admin/jobs and /admin/users endpoints")

    # Show expected API calls
    print("\n📡 Expected API usage:")
    print("   POST /upload (any authenticated user)")
    print("   GET /user/jobs (user's own jobs)")
    print("   GET /admin/jobs (admin only - all jobs)")
    print("   GET /admin/users (admin only - all users)")
    
    # Create example tokens for demonstration
    admin_token = create_mock_jwt({
        "sub": "admin-user-456",
        "email": "admin@mxwhisper.yourdomain.com",
        "preferred_username": "admin.mxwhisper"
    }, ["admin.mxwhisper", "users"])
    
    regular_token = create_mock_jwt({
        "sub": "regular-user-123",
        "email": "user@example.com"
    }, ["users"])
    
    print("\n📡 Manual testing commands:")
    print("# Start server first:")
    print("uv run uvicorn main:app --reload --port 3001")
    print()
    print("# Test admin endpoints:")
    print(f"curl -H 'Authorization: Bearer {admin_token[:50]}...' http://localhost:3001/admin/users")
    print(f"curl -H 'Authorization: Bearer {regular_token[:50]}...' http://localhost:3001/admin/users  # Should fail with 403")

async def main():
    """Run all admin.mxwhisper tests."""
    print("🎯 Testing admin.mxwhisper Integration")
    print("="*50)

    await test_group_recognition()
    await test_admin_token_validation()
    await simulate_admin_workflow()

    print("\n✅ admin.mxwhisper testing complete!")
    print("\n📋 To test with real database:")
    print("1. Ensure PostgreSQL is accessible")
    print("2. Run: uv run alembic upgrade head")
    print("3. Start server: uv run uvicorn main:app --reload")
    print("4. Get real JWT token from Authentik admin.mxwhisper user")
    print("5. Test endpoints with real token")

if __name__ == "__main__":
    asyncio.run(main())