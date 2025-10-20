#!/usr/bin/env python3
"""
Seed Topics Database

This script populates the topics table with an initial hierarchical category structure
for MxWhisper content categorization.

Commands:
    seed                    Seed the database with initial topics (idempotent)
    reset                   Clear all topics and reseed from scratch
    list                    List all topics in a hierarchical view

Usage:
    uv run python scripts/seed_topics.py seed
    uv run python scripts/seed_topics.py reset
    uv run python scripts/seed_topics.py list

Examples:
    # Seed topics (safe to run multiple times)
    uv run python scripts/seed_topics.py seed

    # Reset and reseed all topics (WARNING: deletes all existing topics)
    uv run python scripts/seed_topics.py reset

    # View current topic hierarchy
    uv run python scripts/seed_topics.py list
"""

import os
os.environ['SQLALCHEMY_WARN_20'] = '0'  # Disable SQLAlchemy 2.0 warnings

import asyncio
import argparse
import sys
from pathlib import Path
from typing import List, Optional, Dict

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.data.database import get_db_session
from app.data.models import Topic
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError


# Initial topic hierarchy
INITIAL_TOPICS = [
    {
        "name": "Unknown",
        "description": "Default topic for unclassified or unmatched content",
        "parent": None,
    },
    # Root categories (no parent)
    {
        "name": "Religious",
        "description": "Religious and spiritual content including sermons, Bible studies, and worship",
        "parent": None,
    },
    {
        "name": "Educational",
        "description": "Educational and instructional content including courses, tutorials, and lectures",
        "parent": None,
    },
    {
        "name": "Entertainment",
        "description": "Entertainment and media content including podcasts, audiobooks, and interviews",
        "parent": None,
    },
    {
        "name": "Professional",
        "description": "Professional and business content including meetings and presentations",
        "parent": None,
    },

    # Religious subcategories
    {
        "name": "Bible Study",
        "description": "Bible studies, scriptural analysis, and theological discussions",
        "parent": "Religious",
    },
    {
        "name": "Sermons",
        "description": "Sermons, preaching, and pastoral messages",
        "parent": "Religious",
    },
    {
        "name": "Prayer",
        "description": "Prayer sessions, devotionals, and spiritual meditation",
        "parent": "Religious",
    },
    {
        "name": "Worship",
        "description": "Worship music, praise services, and liturgical content",
        "parent": "Religious",
    },
    {
        "name": "Theology",
        "description": "Theological discussions, doctrine, and religious philosophy",
        "parent": "Religious",
    },

    # Educational subcategories
    {
        "name": "Courses",
        "description": "Educational courses, structured lessons, and academic lectures",
        "parent": "Educational",
    },
    {
        "name": "Tutorials",
        "description": "How-to guides, instructional content, and skill-building tutorials",
        "parent": "Educational",
    },
    {
        "name": "Conferences",
        "description": "Conference talks, academic presentations, and symposiums",
        "parent": "Educational",
    },
    {
        "name": "Lectures",
        "description": "Academic lectures, educational talks, and teaching sessions",
        "parent": "Educational",
    },

    # Entertainment subcategories
    {
        "name": "Podcasts",
        "description": "Podcast episodes, talk shows, and audio programs",
        "parent": "Entertainment",
    },
    {
        "name": "Audiobooks",
        "description": "Audiobook recordings, narrated books, and spoken literature",
        "parent": "Entertainment",
    },
    {
        "name": "Interviews",
        "description": "Interviews, conversations, and Q&A sessions",
        "parent": "Entertainment",
    },
    {
        "name": "Music",
        "description": "Music recordings, concerts, and musical performances",
        "parent": "Entertainment",
    },

    # Professional subcategories
    {
        "name": "Meetings",
        "description": "Business meetings, team discussions, and organizational calls",
        "parent": "Professional",
    },
    {
        "name": "Presentations",
        "description": "Professional presentations, business pitches, and corporate talks",
        "parent": "Professional",
    },
    {
        "name": "Webinars",
        "description": "Online seminars, virtual workshops, and training sessions",
        "parent": "Professional",
    },
]


async def get_or_create_topic(
    db,
    name: str,
    description: Optional[str],
    parent_name: Optional[str] = None,
    topic_cache: Dict[str, Topic] = None
) -> Topic:
    """
    Get existing topic or create a new one.
    Uses a cache to avoid repeated database lookups.
    """
    if topic_cache is None:
        topic_cache = {}

    # Check cache first
    if name in topic_cache:
        return topic_cache[name]

    # Check database
    result = await db.execute(select(Topic).where(Topic.name == name))
    topic = result.scalar_one_or_none()

    if topic:
        topic_cache[name] = topic
        return topic

    # Create new topic
    parent_id = None
    if parent_name:
        parent = await get_or_create_topic(db, parent_name, None, None, topic_cache)
        parent_id = parent.id

    topic = Topic(
        name=name,
        description=description,
        parent_id=parent_id
    )
    db.add(topic)
    await db.flush()  # Get the ID without committing
    topic_cache[name] = topic

    return topic


async def seed_topics():
    """Seed the database with initial topics (idempotent)."""
    print("🌱 Seeding topics database...")

    db = await get_db_session()
    try:
        topic_cache = {}
        created_count = 0
        existing_count = 0

        for topic_data in INITIAL_TOPICS:
            name = topic_data["name"]
            description = topic_data["description"]
            parent_name = topic_data.get("parent")

            # Check if topic already exists
            result = await db.execute(select(Topic).where(Topic.name == name))
            existing_topic = result.scalar_one_or_none()

            if existing_topic:
                existing_count += 1
                topic_cache[name] = existing_topic
                print(f"   ✓ {name} (already exists)")
            else:
                topic = await get_or_create_topic(
                    db, name, description, parent_name, topic_cache
                )
                created_count += 1
                print(f"   + {name} (created)")

        await db.commit()

        print(f"\n✅ Seeding complete!")
        print(f"   Created: {created_count} topics")
        print(f"   Existing: {existing_count} topics")
        print(f"   Total: {created_count + existing_count} topics")

    except Exception as e:
        await db.rollback()
        print(f"\n❌ Error seeding topics: {e}")
        sys.exit(1)
    finally:
        await db.close()


async def reset_topics():
    """Clear all topics and reseed from scratch."""
    print("⚠️  WARNING: This will delete ALL existing topics!")
    print("   This includes any custom topics you've created.")
    response = input("   Are you sure you want to continue? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("❌ Reset cancelled.")
        return

    print("\n🗑️  Resetting topics database...")

    db = await get_db_session()
    try:
        # Delete all topics (cascade will handle job_topics relationships)
        result = await db.execute(delete(Topic))
        deleted_count = result.rowcount
        await db.commit()
        print(f"   Deleted {deleted_count} topics")

        await db.close()

        # Now seed with initial topics
        await seed_topics()

    except Exception as e:
        await db.rollback()
        print(f"\n❌ Error resetting topics: {e}")
        sys.exit(1)
    finally:
        await db.close()


async def list_topics():
    """List all topics in a hierarchical view."""
    print("📋 Topic Hierarchy:\n")

    db = await get_db_session()
    try:
        # Get all topics
        result = await db.execute(select(Topic).order_by(Topic.parent_id, Topic.name))
        topics = result.scalars().all()

        if not topics:
            print("   No topics found. Run 'seed' command to populate initial topics.")
            return

        # Build hierarchy
        topic_dict = {t.id: t for t in topics}
        root_topics = [t for t in topics if t.parent_id is None]

        def print_topic(topic: Topic, indent: int = 0):
            prefix = "   " * indent
            icon = "📁" if indent == 0 else "└─"
            print(f"{prefix}{icon} {topic.name}")
            if topic.description and indent == 0:
                print(f"{prefix}   {topic.description}")

            # Print children
            children = [t for t in topics if t.parent_id == topic.id]
            for child in sorted(children, key=lambda x: x.name):
                print_topic(child, indent + 1)

        for root in sorted(root_topics, key=lambda x: x.name):
            print_topic(root)
            print()

        print(f"Total topics: {len(topics)}")

    except Exception as e:
        print(f"\n❌ Error listing topics: {e}")
        sys.exit(1)
    finally:
        await db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed topics database for MxWhisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        'command',
        choices=['seed', 'reset', 'list'],
        help='Command to execute'
    )

    args = parser.parse_args()

    if args.command == 'seed':
        asyncio.run(seed_topics())
    elif args.command == 'reset':
        asyncio.run(reset_topics())
    elif args.command == 'list':
        asyncio.run(list_topics())


if __name__ == "__main__":
    main()
