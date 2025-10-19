#!/usr/bin/env python3
"""
Manage Users

This script provides user management operations for MxWhisper.

Commands:
    list                           List all users with their details
    create <username> <email>      Create a new user in Authentik and database with JWT token
    delete <username>              Delete a user from both database and Authentik
    update <username>              Update user details in database

Usage:
    uv run python scripts/manage_users.py list
    uv run python scripts/manage_users.py create <username> <email> [OPTIONS]
    uv run python scripts/manage_users.py delete <username> [OPTIONS]
    uv run python scripts/manage_users.py update <username> [OPTIONS]

Examples:
    # List all users
    uv run python scripts/manage_users.py list

    # Create a regular user
    uv run python scripts/manage_users.py create john.doe john@example.com

    # Create an admin user with custom token expiration
    uv run python scripts/manage_users.py create admin.user admin@example.com --role admin --token-days 90

    # Delete user (with confirmation)
    uv run python scripts/manage_users.py delete john.doe

    # Delete user without confirmation
    uv run python scripts/manage_users.py delete john.doe --force

    # Update user email and name
    uv run python scripts/manage_users.py update john.doe --email newemail@example.com --name "John Doe"

    # Change user role
    uv run python scripts/manage_users.py update john.doe --role admin
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import select, func
from app.data import User, Job, Role, get_db_session
from app.auth import authentik_client, create_service_account_token
from app.services.user_service import UserService
from app.config import settings

# Load environment variables
load_dotenv()


async def list_users():
    """List all users with their details."""
    db = None
    try:
        db = await get_db_session()

        # Get all users
        result = await db.execute(select(User))
        users = result.scalars().all()

        if not users:
            print("No users found in database")
            return

        print("=" * 120)
        print(f"{'Username':<20} {'User ID':<15} {'Email':<30} {'Role':<10} {'Token Status':<15} {'Jobs':<10}")
        print("=" * 120)

        for user in users:
            # Get token metadata
            token_metadata = await UserService.get_token_metadata(db, user.id)
            if token_metadata:
                if token_metadata["is_expired"]:
                    token_status = "EXPIRED"
                else:
                    token_status = "ACTIVE"
            else:
                token_status = "NO TOKEN"

            # Get job count
            job_count_result = await db.execute(select(func.count(Job.id)).where(Job.user_id == user.id))
            job_count = job_count_result.scalar()

            # Eagerly load role
            await db.refresh(user, ['role'])
            role_name = user.role.name if user.role else "N/A"

            username = user.preferred_username or "N/A"
            user_id = str(user.id)[:15] if len(str(user.id)) > 15 else str(user.id)
            email = user.email[:30] if len(user.email) > 30 else user.email

            print(f"{username:<20} {user_id:<15} {email:<30} {role_name:<10} {token_status:<15} {job_count:<10}")

        print("=" * 120)

    except Exception as e:
        print(f"❌ Failed to list users: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


async def create_user(username: str, email: str, name: str = None, role: str = "user",
                     token_days: int = None):
    """Create a new user with Authentik integration and service account JWT token."""

    # Set default name if not provided
    if not name:
        name = username

    # Get token expiry
    if token_days is None:
        token_expiry_days = getattr(settings, 'default_token_expiry_days', 365)
    else:
        token_expiry_days = token_days

    print(f"🔧 Creating user account...")
    print(f"   Username: {username}")
    print(f"   Email: {email}")
    print(f"   Name: {name}")
    print(f"   Role: {role}")
    print(f"   Token expiration: {token_expiry_days} days")
    print()

    db = None
    try:
        # Step 1: Create user in Authentik
        print("📡 Creating user in Authentik...")

        # Group names for Authentik
        groups = ["users"] if role == "user" else ["users", "admin.mxwhisper"]

        authentik_user_data = {
            "username": username,
            "email": email,
            "name": name,
            "password": f"service-account-{username}",  # Auto-generated password
            "groups": groups
        }
        authentik_user = await authentik_client.create_user(authentik_user_data)
        authentik_user_pk = authentik_user["pk"]
        print("✅ Authentik user created successfully!")

        # Step 2: Create user in our database
        print("💾 Creating user in database...")
        db = await get_db_session()

        # Ensure roles exist
        await UserService.initialize_roles(db)

        # Map user data to our database format
        db_user_data = {
            "sub": str(authentik_user_pk),
            "email": email,
            "name": name,
            "preferred_username": username,
            "groups": [f"users.mxwhisper"] + ([f"admin.mxwhisper"] if role == "admin" else [])
        }

        database_user = await UserService.create_or_update_user(db, db_user_data)

        # Eagerly load the role relationship
        await db.refresh(database_user, ['role'])

        print("✅ Database user created successfully!")

        # Get role name before closing session
        role_name = database_user.role.name if database_user.role else role

        print("✅ User account created successfully!")
        print(f"   User ID: {database_user.id}")
        print(f"   Username: {database_user.preferred_username}")
        print(f"   Email: {database_user.email}")
        print(f"   Role: {role_name}")
        print()

        # Step 3: Generate service account JWT token
        print("🔑 Generating service account JWT token...")

        # Create token data
        token_data = {
            'sub': str(database_user.id),
            'preferred_username': database_user.preferred_username,
            'email': database_user.email,
            'name': database_user.name,
            'groups': [f'users.mxwhisper'] + ([f'admin.mxwhisper'] if role == 'admin' else [])
        }

        # Create JWT token
        token = create_service_account_token(token_data, expires_days=token_expiry_days)
        expires_at = datetime.utcnow() + timedelta(days=token_expiry_days)

        # Store token metadata in database
        await UserService.store_token_metadata(
            db=db,
            user_id=database_user.id,
            expires_at=expires_at
        )

        print(f"✅ Service account JWT token generated!")
        print()
        print("=" * 80)
        print("🔑 NEW TOKEN (save this - it will only be shown once!):")
        print("=" * 80)
        print(token)
        print("=" * 80)
        print()
        print("📋 API Usage:")
        print(f'curl -H "Authorization: Bearer {token[:50]}..." \\')
        print('     -F "file=@audio.mp3" \\')
        print('     http://localhost:8000/upload')
        print()
        print("⚠️  SECURITY WARNING:")
        print(f"   • This token expires on: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("   • Store it securely in your application")
        print("   • Never commit it to version control")
        print(f"   • Rotate before expiration ({token_expiry_days} days)")
        print("   • This is a self-signed JWT token for API access")
        print()
        print("🔐 Token Details:")
        print(f"   • User ID: {database_user.id}")
        print(f"   • Username: {database_user.preferred_username}")
        print(f"   • Token Type: Service Account JWT")
        print(f"   • Role: {role}")
        print(f"   • Permissions: {'Full admin access' if role == 'admin' else 'User access only'}")
        print(f"   • Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()
        print("🔄 Token Management:")
        print(f"   • List tokens: uv run python scripts/manage_tokens.py list")
        print(f"   • Revoke token: uv run python scripts/manage_tokens.py revoke {username}")
        print(f"   • Rotate token: uv run python scripts/manage_tokens.py rotate {username}")

        return True

    except Exception as e:
        print(f"❌ Failed to create user: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            await db.close()


async def delete_user(username: str, force: bool = False):
    """Delete a user from both the database and Authentik."""
    db = None
    try:
        db = await get_db_session()

        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found in database")
            return False

        # Check for associated jobs
        job_count_result = await db.execute(select(func.count(Job.id)).where(Job.user_id == user.id))
        job_count = job_count_result.scalar()

        print(f"📋 User Details:")
        print(f"   Username: {user.preferred_username}")
        print(f"   Email: {user.email}")
        print(f"   User ID: {user.id}")
        print(f"   Associated Jobs: {job_count}")

        if user.token_expires_at and user.token_expires_at > datetime.utcnow():
            print(f"   Active Token: Expires {user.token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        print()

        # Warn about jobs
        if job_count > 0:
            print(f"⚠️  WARNING: This user has {job_count} associated job(s)")
            print("   Deleting the user will also delete all their jobs!")
            print()

        # Confirmation
        if not force:
            confirm_msg = f"Are you sure you want to delete user '{username}' from both database and Authentik? (y/N): "
            response = input(confirm_msg)
            if response.lower() != 'y':
                print("❌ Deletion cancelled")
                return False

        print()

        # Clear token metadata (JWT tokens can't be revoked, they expire naturally)
        if user.token_expires_at and user.token_expires_at > datetime.utcnow():
            print("🔄 Clearing token metadata...")
            await UserService.clear_token_metadata(db, user.id)
            print("✅ Token metadata cleared")

        # Delete from database
        print("🗑️  Deleting user from database...")
        await db.delete(user)
        await db.commit()
        print("✅ User deleted from database")

        # Delete from Authentik
        print("🗑️  Deleting user from Authentik...")
        try:
            # Get Authentik user
            authentik_user = await authentik_client.get_user_by_username(username)
            if authentik_user:
                # Delete the user from Authentik
                deletion_success = await authentik_client.delete_user(authentik_user['pk'])
                if deletion_success:
                    print("✅ User deleted from Authentik")
                else:
                    print("⚠️  Failed to delete user from Authentik")
                    print(f"   You may need to delete user manually from Authentik UI (User PK: {authentik_user['pk']})")
            else:
                print("ℹ️  User not found in Authentik (already deleted or never existed)")
        except Exception as e:
            print(f"⚠️  Warning: Failed to check Authentik: {e}")

        print()
        print(f"✅ User '{username}' deleted successfully!")
        return True

    except Exception as e:
        print(f"❌ Failed to delete user: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            await db.close()


async def update_user(username: str, email: str = None, name: str = None, role: str = None):
    """Update user details."""
    db = None
    try:
        db = await get_db_session()

        # Find the user
        result = await db.execute(select(User).where(User.preferred_username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User '{username}' not found in database")
            return False

        print(f"📋 Current User Details:")
        print(f"   Username: {user.preferred_username}")
        print(f"   Email: {user.email}")
        print(f"   Name: {user.name}")

        # Eagerly load role
        await db.refresh(user, ['role'])
        current_role = user.role.name if user.role else "N/A"
        print(f"   Role: {current_role}")
        print()

        # Track what's being updated
        updates = []

        # Update email
        if email and email != user.email:
            user.email = email
            updates.append(f"Email: {email}")

        # Update name
        if name and name != user.name:
            user.name = name
            updates.append(f"Name: {name}")

        # Update role
        if role and role != current_role:
            # Get the new role
            role_result = await db.execute(select(Role).where(Role.name == role))
            new_role = role_result.scalar_one_or_none()

            if not new_role:
                print(f"❌ Role '{role}' not found")
                return False

            user.role_id = new_role.id
            updates.append(f"Role: {role}")

        # Check if anything changed
        if not updates:
            print("ℹ️  No changes to apply")
            return True

        # Save changes
        print("💾 Updating user...")
        await db.commit()
        await db.refresh(user)

        print("✅ User updated successfully!")
        print()
        print("📋 Updated fields:")
        for update in updates:
            print(f"   • {update}")

        return True

    except Exception as e:
        print(f"❌ Failed to update user: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            await db.close()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage users in MxWhisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # List command
    subparsers.add_parser('list', help='List all users with their details')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new user')
    create_parser.add_argument('username', help='Username for the new user')
    create_parser.add_argument('email', help='Email address for the new user')
    create_parser.add_argument('--name', help='Display name (defaults to username)')
    create_parser.add_argument('--role', choices=['user', 'admin'], default='user',
                              help='Role to assign (default: user)')
    create_parser.add_argument('--token-days', type=int, default=None,
                              help='Days until token expires (default: 365)')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a user')
    delete_parser.add_argument('username', help='Username of the user to delete')
    delete_parser.add_argument('--force', action='store_true',
                              help='Skip confirmation prompt')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update user details')
    update_parser.add_argument('username', help='Username of the user to update')
    update_parser.add_argument('--email', help='New email address')
    update_parser.add_argument('--name', help='New display name')
    update_parser.add_argument('--role', choices=['user', 'admin'], help='New role')

    return parser.parse_args()


async def main():
    """Main script execution."""
    args = parse_arguments()

    if args.command == 'list':
        print("📋 MxWhisper User List")
        print("=" * 120)
        print()
        await list_users()
    elif args.command == 'create':
        print("🚀 MxWhisper User Creation")
        print("=" * 50)
        print()
        success = await create_user(
            username=args.username,
            email=args.email,
            name=args.name,
            role=args.role,
            token_days=args.token_days
        )
        if not success:
            sys.exit(1)
    elif args.command == 'delete':
        print("🗑️  MxWhisper User Deletion")
        print("=" * 50)
        print()
        success = await delete_user(
            username=args.username,
            force=args.force
        )
        if not success:
            sys.exit(1)
    elif args.command == 'update':
        print("🔄 MxWhisper User Update")
        print("=" * 50)
        print()
        success = await update_user(
            username=args.username,
            email=args.email,
            name=args.name,
            role=args.role
        )
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
