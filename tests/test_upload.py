#!/usr/bin/env python3
"""
Test the file upload and job creation API
"""

import asyncio
import os
from datetime import datetime, timedelta

import httpx
from jose import jwt
import pytest

# Mock JWT secret for testing (same as in auth.py)
JWT_SECRET = "your-secret-key-here"
JWT_ALGORITHM = "HS256"

def create_test_jwt() -> str:
    """Create a mock JWT token for testing."""
    payload = {
        "sub": "test-user-123",
        "email": "test@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "groups": ["users"]
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

@pytest.mark.asyncio
async def test_file_upload():
    """Test the file upload and job creation."""
    print("🧪 Testing file upload and job creation...")

    # Create test JWT token
    token = create_test_jwt()
    print(f"📝 Created test JWT token for user: testuser")

    # Create a test file
    test_file_path = "/home/geo/develop/mxwhisper/tests/data/who_is_jesus.mp3"
    print(f"📄 Using test audio file: {test_file_path}")
    
    # Check if file exists
    if not os.path.exists(test_file_path):
        print(f"❌ Test file not found: {test_file_path}")
        return False

    try:
        # Upload the file
        async with httpx.AsyncClient() as client:
            with open(test_file_path, "rb") as f:
                files = {"file": ("who_is_jesus.mp3", f, "audio/mpeg")}
                # No authorization header needed for testing

                response = await client.post(
                    "http://localhost:3001/upload",
                    files=files,
                    timeout=60.0  # Increased timeout for audio processing
                )

                print(f"📡 Upload response status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    print("✅ File uploaded successfully!")
                    print(f"   Job ID: {result['job_id']}")
                    print(f"   Message: {result['message']}")

                    # Test getting job status
                    job_id = result['job_id']
                    print(f"\n🔍 Checking job status for ID: {job_id}")

                    status_response = await client.get(
                        f"http://localhost:3001/jobs/{job_id}",
                        timeout=10.0
                    )

                    if status_response.status_code == 200:
                        job_data = status_response.json()
                        print("✅ Job status retrieved!")
                        print(f"   Filename: {job_data['filename']}")
                        print(f"   Status: {job_data['status']}")
                        print(f"   Created: {job_data['created_at']}")
                    else:
                        print(f"❌ Failed to get job status: {status_response.text}")

                else:
                    print(f"❌ Upload failed: {response.text}")

    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # No cleanup needed - using existing test file
        print(f"📄 Test completed with file: {test_file_path}")

async def main():
    """Run the upload test."""
    print("🎯 Testing File Upload and Job Creation API")
    print("="*45)

    await test_file_upload()

    print("\n✅ Upload testing complete!")

if __name__ == "__main__":
    asyncio.run(main())