#!/usr/bin/env python3
"""
API Service Account Creation Script

This script creates service accounts with non-expiring JWT tokens for API access.
These accounts can be used by applications, services, or automated systems.

Features:
- Creates user in both Authentik and local database
- Generates non-expiring JWT tokens
- Supports user and admin roles
- Outputs token for immediate use

Usage:
    uv run python scripts/create_api_user.py --username my-service --email service@example.com --role admin

Arguments:
    --username: Service account username (required)
    --email: Service account email (required)
    --name: Display name (optional, defaults to username)
    --role: Role to assign (user or admin, default: user)
    --help: Show this help message

Examples:
    # Create admin service account
    uv run python scripts/create_api_user.py --username api-admin --email admin@company.com --role admin

    # Create regular user service account
    uv run python scripts/create_api_user.py --username api-user --email user@company.com --role user

    # Create with custom display name
    uv run python scripts/create_api_user.py --username my-app --email app@company.com --name "My Application" --role user
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from app.auth import authentik_client
from app.services.user_service import create_user_in_authentik_and_db, UserService
from app.auth.jwt import create_access_token
from app.data import async_session, get_db_session
from sqlalchemy import select
from sqlalchemy.orm import joinedload

# Load environment variables
load_dotenv()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create API service accounts with non-expiring tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--username",
        required=True,
        help="Service account username"
    )

    parser.add_argument(
        "--email",
        required=True,
        help="Service account email address"
    )

    parser.add_argument(
        "--name",
        help="Display name (defaults to username)"
    )

    parser.add_argument(
        "--role",
        choices=["user", "admin"],
        default="user",
        help="Role to assign (default: user)"
    )

    return parser.parse_args()


async def create_api_user(username: str, email: str, name: str, role: str):
    """Create an API service account user."""

    print(f"🔧 Creating API service account...")
    print(f"   Username: {username}")
    print(f"   Email: {email}")
    print(f"   Name: {name}")
    print(f"   Role: {role}")
    print()

    # Create user in both Authentik and database
    # We need to do this in separate steps to avoid async session conflicts
    db = None
    try:
        # Step 1: Create user in Authentik first
        print("📡 Creating user in Authentik...")
        
        # Group names for Authentik (not UUIDs - the client will look up the IDs)
        groups = ["users"] if role == "user" else ["users", "admin.mxwhisper"]
        
        authentik_user_data = {
            "username": username,
            "email": email,
            "name": name,
            "password": f"service-account-{username}",  # Auto-generated password
            "groups": groups
        }
        authentik_user = await authentik_client.create_user(authentik_user_data)
        print("✅ Authentik user created successfully!")
        
        # Step 2: Create user in our database
        print("💾 Creating user in database...")
        db = await get_db_session()
        
        # Map Authentik user data to our database format
        db_user_data = {
            "sub": str(authentik_user["pk"]),  # Use Authentik user ID
            "email": authentik_user["email"],
            "name": authentik_user["name"],
            "preferred_username": authentik_user["username"],
            "groups": groups
        }
        
        database_user = await UserService.create_or_update_user(db, db_user_data)
        
        # Eagerly load the role relationship
        await db.refresh(database_user, ['role'])
        
        print("✅ Database user created successfully!")
        
        # Get role name before closing session
        role_name = database_user.role.name if database_user.role else role
        
        print("✅ Service account created successfully!")
        print(f"   User ID: {database_user.id}")
        print(f"   Username: {database_user.preferred_username}")
        print(f"   Email: {database_user.email}")
        print(f"   Role: {role_name}")
        print()

        # Generate non-expiring JWT token
        print("🔑 Generating non-expiring JWT token...")

        token_data = {
            'sub': str(database_user.id),
            'preferred_username': database_user.preferred_username,
            'email': database_user.email,
            'name': database_user.name,
            'groups': [f'users.mxwhisper'] + ([f'admin.mxwhisper'] if role == 'admin' else [])
        }

        token = create_access_token(token_data, never_expire=True)

        print("✅ Non-expiring JWT token generated!")
        print("=" * 80)
        print(token)
        print("=" * 80)
        print()
        print("📋 API Usage:")
        print(f"curl -H \"Authorization: Bearer {token[:50]}...\" \\")
        print("     -F \"file=@audio.mp3\" \\")
        print("     http://localhost:8000/upload")
        print()
        print("⚠️  SECURITY WARNING:")
        print("   • This token NEVER expires")
        print("   • Store it securely in your application")
        print("   • Never commit it to version control")
        print("   • Rotate periodically for security")
        print()
        print("🔐 Token Details:")
        print(f"   • User ID: {database_user.id}")
        print(f"   • Username: {database_user.preferred_username}")
        print(f"   • Role: {role}")
        print(f"   • Permissions: {'Full admin access' if role == 'admin' else 'User access only'}")

        return token

    except Exception as e:
        print(f"❌ Failed to create service account: {e}")
        return None
    finally:
        if db:
            await db.close()


async def main():
    """Main script execution."""
    print("🚀 MxWhisper API Service Account Creator")
    print("=" * 50)

    args = parse_arguments()

    # Set default name if not provided
    name = args.name if args.name else args.username

    # Create the service account
    token = await create_api_user(
        username=args.username,
        email=args.email,
        name=name,
        role=args.role
    )

    if token:
        print("🎉 Service account creation completed successfully!")
        print("\n💡 Next steps:")
        print("   1. Store the token securely in your application")
        print("   2. Test the token with: curl -H \"Authorization: Bearer <token>\" http://localhost:8000/admin/jobs")
        print("   3. Use the token in your API client code")
    else:
        print("❌ Service account creation failed!")
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())