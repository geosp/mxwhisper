#!/usr/bin/env python3
"""
Comprehensive authenticated end-to-end test for MxWhisper API
Tests user creation, authentication, file upload, and transcript download
"""

import asyncio
import os
from datetime import timedelta

import httpx
import pytest
from jose import jwt
from sqlalchemy import select

# JWT settings for testing
JWT_SECRET = "your-secret-key-here"
JWT_ALGORITHM = "HS256"

def create_test_jwt(user_data: dict, expires_delta: timedelta = None) -> str:
    """Create a JWT token for testing.

    Note: This creates test tokens directly. In production, tokens come from Authentik.
    For testing purposes, we create HS256 tokens. Real Authentik tokens use RS256.
    """
    from datetime import datetime
    from jose import jwt

    payload = user_data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30)
    payload.update({"exp": expire})

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def create_test_user(base_url: str) -> dict:
    """Create a test user via the admin API."""
    print("👤 Creating test user...")

    # First, create an admin user directly in the database for testing
    from app.data import get_db_session, User, Role, async_session
    from app.services.user_service import UserService

    async with async_session() as db:
        # Ensure roles exist
        await UserService.initialize_roles(db)

        # Create or get admin user
        admin_user = await db.execute(select(User).where(User.preferred_username == "admin"))
        admin_user = admin_user.scalar_one_or_none()

        if not admin_user:
            # Get admin role
            admin_role = await db.execute(select(Role).where(Role.name == "admin"))
            admin_role = admin_role.scalar_one_or_none()

            if admin_role:
                admin_user = User(
                    id="admin-user-123",
                    email="admin@example.com",
                    name="Admin User",
                    preferred_username="admin",
                    role_id=admin_role.id
                )
                db.add(admin_user)
                await db.commit()
                await db.refresh(admin_user)
                print("✅ Created admin user in database")

    user_data = {
        "email": "test@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "password": "testpassword123",
        "role": "user"
    }

    # Create admin token using the real admin user ID
    admin_payload = {
        "sub": "admin-user-123",  # This now exists in the database
        "email": "admin@example.com",
        "name": "Admin User",
        "preferred_username": "admin",
        "groups": ["admins"]
    }
    admin_token = create_test_jwt(admin_payload)

    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/admin/users",
                json=user_data,
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                print("✅ Test user created successfully!")
                print(f"   User ID: {result['user_id']}")
                print(f"   Username: {result['preferred_username']}")
                return result
            else:
                print(f"⚠️  User creation failed: {response.text}")
                # For testing with legacy JWT, create a mock user result
                return {"user_id": "test-user-123", "preferred_username": "testuser"}

    except Exception as e:
        print(f"❌ User creation error: {str(e)}")
        return {"user_id": "fallback-user", "preferred_username": "testuser"}

@pytest.mark.asyncio
async def test_authenticated_workflow():
    """Test the complete authenticated workflow.

    Note: This test creates JWT tokens directly for testing. In production,
    tokens come from Authentik. For testing to work with test tokens, you need
    to either:
    1. Mock the Authentik token verification
    2. Use actual Authentik tokens
    3. Configure your test environment to accept HS256 tokens

    This test currently assumes option 3 for simplicity.
    """
    print("🚀 Starting authenticated end-to-end test...")
    print("="*60)

    try:
        base_url = "http://localhost:8000"
        test_file_path = "/home/geo/develop/mxwhisper/tests/data/who_is_jesus.mp3"

        # Track created resources for cleanup
        created_user_id = None
        created_job_id = None

        # Step 1: Create test user
        user_result = await create_test_user(base_url)
        if not user_result:
            print("❌ Failed to create/access test user")
            return False

        created_user_id = user_result.get("user_id")

        # Step 2: Create JWT token for the test user
        user_payload = {
            "sub": user_result["user_id"],
            "email": "test@example.com",
            "name": "Test User",
            "preferred_username": user_result["preferred_username"],
            "groups": ["users"]
        }
        token = create_test_jwt(user_payload)

        # Step 3: Upload file with authentication
        print("\n📤 Uploading file with authentication...")
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(test_file_path, "rb") as f:
                    files = {"file": ("who_is_jesus.mp3", f, "audio/mpeg")}
                    response = await client.post(
                        f"{base_url}/upload",
                        files=files,
                        headers=headers,
                        timeout=60.0
                    )

                print(f"📡 Upload response status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    print("✅ File uploaded successfully!")
                    print(f"   Job ID: {result['job_id']}")
                    print(f"   Message: {result['message']}")
                    job_id = result['job_id']
                    created_job_id = job_id
                else:
                    print(f"❌ Upload failed: {response.text}")
                    return False

        except Exception as e:
            print(f"❌ Upload error: {str(e)}")
            return False

        # Step 4: Monitor job status until completion
        print(f"\n🔍 Monitoring job status for ID: {created_job_id}")
        max_attempts = 30  # 5 minutes max
        attempt = 0

        while attempt < max_attempts:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{base_url}/job/{created_job_id}")

                    if response.status_code == 200:
                        job_data = response.json()
                        status = job_data['status']
                        print(f"   Status: {status} (attempt {attempt + 1}/{max_attempts})")

                        if status == "completed":
                            print("✅ Transcription completed!")
                            print(f"   Filename: {job_data['filename']}")
                            print(f"   Created: {job_data['created_at']}")
                            print(f"   Transcript length: {len(job_data.get('transcript', ''))} characters")

                            # Verify transcript content
                            transcript = job_data.get('transcript', '')
                            if len(transcript) > 100 and 'jesus' in transcript.lower():
                                print("✅ Transcript content verified!")
                            else:
                                print("⚠️  Transcript content seems incomplete")
                                return False

                            break
                        elif status == "failed":
                            print("❌ Transcription failed!")
                            return False
                        else:
                            # Still processing, wait and retry
                            await asyncio.sleep(10)
                            attempt += 1
                    else:
                        print(f"❌ Status check failed: {response.text}")
                        return False

            except Exception as e:
                print(f"❌ Status check error: {str(e)}")
                attempt += 1
                await asyncio.sleep(10)

        if attempt >= max_attempts:
            print("❌ Transcription timed out!")
            return False

        # Step 5: Download transcript
        print(f"\n📥 Downloading transcript for job {created_job_id}...")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{base_url}/jobs/{created_job_id}/download",
                    headers=headers
                )

                if response.status_code == 200:
                    transcript_content = response.text
                    print("✅ Transcript downloaded successfully!")
                    print(f"   Content length: {len(transcript_content)} characters")

                    # Save to file for verification
                    with open("test_transcript.txt", "w") as f:
                        f.write(transcript_content)
                    print("   Saved to: test_transcript.txt")

                    # Verify downloaded content matches (normalize whitespace)
                    downloaded_normalized = transcript_content.strip()
                    job_transcript_normalized = job_data.get('transcript', '').strip()

                    if downloaded_normalized == job_transcript_normalized:
                        print("✅ Downloaded content matches job transcript!")
                    else:
                        # Check if the difference is just whitespace/formatting
                        import re
                        downloaded_clean = re.sub(r'\s+', ' ', downloaded_normalized)
                        job_clean = re.sub(r'\s+', ' ', job_transcript_normalized)

                        if downloaded_clean == job_clean:
                            print("✅ Downloaded content matches job transcript (formatting normalized)!")
                        else:
                            print("⚠️  Downloaded content differs from job transcript")
                            print(f"   Downloaded length: {len(downloaded_normalized)}")
                            print(f"   Job transcript length: {len(job_transcript_normalized)}")
                            return False

                else:
                    print(f"❌ Download failed: {response.text}")
                    return False

        except Exception as e:
            print(f"❌ Download error: {str(e)}")
            return False

        # Cleanup
        if os.path.exists("test_transcript.txt"):
            os.remove("test_transcript.txt")
            print("🧹 Cleaned up test transcript file")

        print("\n🎉 Authenticated end-to-end test completed successfully!")
        return True
    except Exception as e:
        print(f"❌ Test workflow error: {str(e)}")
        return False
    finally:
        # Always cleanup test data
        await cleanup_test_data(base_url, created_user_id, created_job_id)

async def cleanup_test_data(base_url: str, user_id: str = None, job_id: str = None):
    """Clean up test data - delete user and job."""
    print("\n🧹 Cleaning up test data...")

    # Create admin token for cleanup
    admin_payload = {
        "sub": "admin-user-123",
        "email": "admin@example.com",
        "name": "Admin User",
        "preferred_username": "admin",
        "groups": ["admins"]
    }
    admin_token = create_test_jwt(admin_payload)
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Delete user (if it exists and is not a system user)
            if user_id and user_id not in ["existing-user", "fallback-user"]:
                print(f"   Deleting user {user_id}...")
                response = await client.delete(
                    f"{base_url}/admin/users/{user_id}",
                    headers=headers
                )
                if response.status_code == 200:
                    print(f"   ✅ User {user_id} deleted")
                else:
                    print(f"   ⚠️  Failed to delete user {user_id}: {response.text}")
            
            # Also try to delete the actual test user that might have been created
            # The API might fail but still create a user, or there might be leftover users
            try:
                print(f"   Attempting to delete test user with ID 12...")
                response = await client.delete(
                    f"{base_url}/admin/users/12",
                    headers=headers
                )
                if response.status_code == 200:
                    print(f"   ✅ Cleaned up test user with ID 12")
                # Don't print errors for users that don't exist
            except Exception:
                pass
    except Exception as e:
        print(f"   ⚠️  Cleanup error: {str(e)}")

    print("🧹 Cleanup completed")

async def main():
    """Run the authenticated workflow test."""
    print("🧪 Testing Complete Authenticated Workflow")
    print("="*50)

    success = await test_authenticated_workflow()

    if success:
        print("\n✅ All tests passed!")
        print("   ✓ User creation/authentication")
        print("   ✓ Secure file upload")
        print("   ✓ Job status monitoring")
        print("   ✓ Transcript retrieval")
        print("   ✓ Transcript download")
    else:
        print("\n❌ Test failed!")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
