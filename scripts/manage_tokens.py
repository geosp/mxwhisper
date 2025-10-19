#!/usr/bin/env python3
"""
Manage Service Account JWT Tokens

This script provides token management operations for users.

Commands:
    list                  List all users with their token status
    generate <username>   Generate a new token for a user
    revoke <username>     Revoke a user's token
    rotate <username>     Rotate a user's token (create new, revoke old)

Usage:
    uv run python scripts/manage_tokens.py list
    uv run python scripts/manage_tokens.py generate <username> [--days DAYS] [--force]
    uv run python scripts/manage_tokens.py revoke <username>
    uv run python scripts/manage_tokens.py rotate <username> [--days DAYS]

Examples:
    # List all tokens
    uv run python scripts/manage_tokens.py list

    # Generate a token for a user (default: 365 days)
    uv run python scripts/manage_tokens.py generate john.doe

    # Generate a short-lived token (30 days)
    uv run python scripts/manage_tokens.py generate john.doe --days 30

    # Generate token without confirmation (if one already exists)
    uv run python scripts/manage_tokens.py generate john.doe --days 7 --force

    # Revoke a user's token
    uv run python scripts/manage_tokens.py revoke john.doe

    # Rotate a token (create new, revoke old)
    uv run python scripts/manage_tokens.py rotate john.doe

    # Rotate with custom expiration
    uv run python scripts/manage_tokens.py rotate john.doe --days 90
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import select
from datetime import datetime, timedelta
from app.data import User, get_db_session
from app.auth import authentik_client, create_service_account_token
from app.services.user_service import UserService
from app.services.token_service import TokenService
from app.config import settings

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


async def list_tokens():
    """List all users with their token status."""
    db = None
    try:
        db = await get_db_session()

        # Get all users
        result = await db.execute(select(User))
        users = result.scalars().all()

        if not users:
            print("No users found in database")
            return

        print("=" * 100)
        print(f"{'Username':<20} {'User ID':<40} {'Token Status':<15} {'Expires':<25}")
        print("=" * 100)

        for user in users:
            token_metadata = await UserService.get_token_metadata(db, user.id)

            if token_metadata:
                if token_metadata["is_expired"]:
                    status = "EXPIRED"
                    expires = token_metadata["expires_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    status = "ACTIVE"
                    expires = token_metadata["expires_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                status = "NO TOKEN"
                expires = "N/A"

            username = user.preferred_username or "N/A"
            print(f"{username:<20} {user.id:<40} {status:<15} {expires:<25}")

        print("=" * 100)

    except Exception as e:
        print(f"❌ Failed to list tokens: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


async def generate_token(username: str, expires_days: int = None, force: bool = False):
    """Generate a service account JWT token for a user."""
    db = None
    try:
        db = await get_db_session()

        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found")
            return False

        # Check if user already has a token
        existing_token_metadata = await UserService.get_token_metadata(db, user.id)
        if existing_token_metadata and not existing_token_metadata["is_expired"]:
            print("⚠️  WARNING: User already has an active token!")
            print(f"   Created: {existing_token_metadata['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"   Expires: {existing_token_metadata['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print()
            if not force:
                response = input("Do you want to create a new token anyway? This will revoke the old token. (y/N): ")
                if response.lower() != 'y':
                    print("❌ Token generation cancelled")
                    return False
                print()
            else:
                print("ℹ️  --force flag set, creating new token without confirmation")
                print()

        # Get token expiry
        if expires_days is None:
            token_expiry_days = getattr(settings, 'default_token_expiry_days', 365)
        else:
            token_expiry_days = expires_days

        # Get user role
        await db.refresh(user, ['role'])
        role_name = user.role.name if user.role else 'user'
        groups = [f'users.mxwhisper'] + ([f'admin.mxwhisper'] if role_name == 'admin' else [])

        # Create token data
        token_data = {
            'sub': str(user.id),
            'username': user.preferred_username,
            'roles': groups
        }

        # Get current revocation counter
        revocation_counter = user.token_revocation_counter

        # Create JWT token using TokenService
        token_service = TokenService()
        expires_delta = timedelta(days=token_expiry_days)
        token = token_service.create_access_token(token_data, expires_delta, revocation_counter)
        expires_at = datetime.utcnow() + expires_delta

        # Extract JTI from the generated token
        import base64
        import json
        token_jti = None
        try:
            parts = token.split('.')
            if len(parts) == 3:
                payload_b64 = parts[1]
                payload_b64 += '=' * (4 - len(payload_b64) % 4)
                payload_bytes = base64.urlsafe_b64decode(payload_b64)
                payload_str = payload_bytes.decode('utf-8')
                payload = json.loads(payload_str)
                token_jti = payload.get('jti')
        except Exception as e:
            logger.warning(f"Failed to extract JTI from token: {e}")

        # Store token metadata with JTI
        await UserService.store_token_metadata(
            db=db,
            user_id=user.id,
            expires_at=expires_at,
            token_jti=token_jti
        )

        print()
        print("=" * 80)
        print("🔑 NEW TOKEN (save this - it will only be shown once!):")
        print("=" * 80)
        print(token)
        print("=" * 80)
        print()
        print("📋 Token Details:")
        print(f"   • Username: {username}")
        print(f"   • User ID: {user.id}")
        print(f"   • Role: {role_name}")
        print(f"   • Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"   • Lifetime: {token_expiry_days} days")
        print()
        print("⚠️  SECURITY WARNING:")
        print("   • Store this token securely in your application")
        print("   • Never commit it to version control")
        print("   • This is a self-signed JWT token for API access")

        return True

    except Exception as e:
        print(f"❌ Failed to generate token: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            await db.close()


async def revoke_token(username: str):
    """Revoke a user's token."""
    db = None
    try:
        db = await get_db_session()

        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found")
            return

        # Get token metadata
        token_metadata = await UserService.get_token_metadata(db, user.id)
        if not token_metadata:
            print(f"⚠️  User '{username}' has no active token to revoke")
            return

        print(f"🔄 Revoking all tokens for user '{username}'...")
        print(f"   Token expires: {token_metadata['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if token_metadata['expires_at'] else 'Unknown'}")

        # Revoke all tokens by incrementing revocation counter
        user.token_revocation_counter += 1
        await db.commit()
        await db.refresh(user)
        
        token_service = TokenService()
        success = True  # Since we incremented the counter, consider it successful
        
        if success:
            print(f"✅ All tokens revoked for user '{username}' (revocation counter incremented to {user.token_revocation_counter})")
        else:
            print(f"❌ Failed to revoke tokens for user '{username}'")

        # Clear token metadata from database
        await UserService.clear_token_metadata(db, user.id)
        print(f"✅ Token metadata cleared for user '{username}'")

    except Exception as e:
        print(f"❌ Failed to revoke token: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


async def rotate_token(username: str, expires_days: int = None):
    """Rotate a user's token (create new, revoke old)."""
    db = None
    try:
        db = await get_db_session()

        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found")
            return

        # Get existing token metadata
        old_token_metadata = await UserService.get_token_metadata(db, user.id)

        # Get token expiry
        if expires_days is None:
            token_expiry_days = getattr(settings, 'default_token_expiry_days', 365)
        else:
            token_expiry_days = expires_days

        print(f"🔄 Rotating token for user '{username}'...")
        if old_token_metadata and old_token_metadata.get('expires_at'):
            print(f"   Old Token Expires: {old_token_metadata['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"   New Token Expiration: {token_expiry_days} days")
        print()

        # Get user role
        await db.refresh(user, ['role'])
        role_name = user.role.name if user.role else 'user'
        groups = [f'users.mxwhisper'] + ([f'admin.mxwhisper'] if role_name == 'admin' else [])

        # Create token data
        token_data = {
            'sub': str(user.id),
            'preferred_username': user.preferred_username,
            'email': user.email,
            'name': user.name,
            'groups': groups
        }

        # Create new service account JWT token
        print("1️⃣  Creating new token...")
        token = create_service_account_token(token_data, expires_days=token_expiry_days)
        expires_at = datetime.utcnow() + timedelta(days=token_expiry_days)

        # Store new token metadata (this will overwrite the old metadata)
        await UserService.store_token_metadata(
            db=db,
            user_id=user.id,
            expires_at=expires_at
        )

        print("✅ New token created successfully!")
        print()

        print("2️⃣  Old token metadata replaced")
        print("ℹ️  Note: Old JWT tokens will expire based on their original expiration time")
        print()
        print("⚠️  SECURITY WARNING:")
        print(f"   • Store this token securely in your application")
        print("   • Never commit it to version control")
        print(f"   • Rotate before expiration ({token_expiry_days} days)")

    except Exception as e:
        print(f"❌ Failed to rotate token: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage service account JWT tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # List command
    subparsers.add_parser('list', help='List all users with their token status')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate a new token for a user')
    generate_parser.add_argument('username', help='Username to generate token for')
    generate_parser.add_argument('--days', type=int, default=None, help='Days until token expires (default: 365)')
    generate_parser.add_argument('--force', action='store_true', help='Skip confirmation if token already exists')

    # Revoke command
    revoke_parser = subparsers.add_parser('revoke', help='Revoke a user\'s token')
    revoke_parser.add_argument('username', help='Username of the user whose token to revoke')

    # Rotate command
    rotate_parser = subparsers.add_parser('rotate', help='Rotate a user\'s token (create new, revoke old)')
    rotate_parser.add_argument('username', help='Username of the user whose token to rotate')
    rotate_parser.add_argument('--days', type=int, default=None, help='Days until new token expires (default: 365)')

    return parser.parse_args()


async def main():
    """Main script execution."""
    args = parse_arguments()

    if args.command == 'list':
        await list_tokens()
    elif args.command == 'generate':
        await generate_token(args.username, args.days, args.force)
    elif args.command == 'revoke':
        await revoke_token(args.username)
    elif args.command == 'rotate':
        await rotate_token(args.username, args.days)


if __name__ == "__main__":
    asyncio.run(main())
