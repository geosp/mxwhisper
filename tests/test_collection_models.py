#!/usr/bin/env python3
"""
Unit tests for Topic, Collection, JobTopic, and JobCollection models.

Tests cover:
- Topic hierarchy (parent-child relationships)
- Collection creation and ownership
- JobTopic with AI confidence and reasoning
- JobCollection with position ordering
- Unique constraints
- Cascade deletes
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.data.database import async_session
from app.data.models import User, Job, Topic, Collection, JobTopic, JobCollection, Role


@pytest.mark.asyncio
class TestTopicModel:
    """Test Topic model and hierarchy."""

    async def test_create_topic(self):
        """Test creating a basic topic."""
        async with async_session() as db:
            topic = Topic(
                name="Test Topic",
                description="A test topic for unit testing"
            )
            db.add(topic)
            await db.commit()
            await db.refresh(topic)

            assert topic.id is not None
            assert topic.name == "Test Topic"
            assert topic.description == "A test topic for unit testing"
            assert topic.parent_id is None
            assert topic.created_at is not None

            # Cleanup
            await db.delete(topic)
            await db.commit()

    async def test_topic_hierarchy(self):
        """Test parent-child topic relationships."""
        async with async_session() as db:
            # Create parent topic
            parent = Topic(name="Parent Topic", description="Parent category")
            db.add(parent)
            await db.commit()
            await db.refresh(parent)

            # Create child topic
            child = Topic(
                name="Child Topic",
                description="Child category",
                parent_id=parent.id
            )
            db.add(child)
            await db.commit()
            await db.refresh(child)

            assert child.parent_id == parent.id

            # Test relationship navigation
            result = await db.execute(
                select(Topic).where(Topic.id == child.id)
            )
            child_from_db = result.scalar_one()
            assert child_from_db.parent.name == "Parent Topic"

            # Test children backref
            result = await db.execute(
                select(Topic).where(Topic.id == parent.id)
            )
            parent_from_db = result.scalar_one()
            assert len(parent_from_db.children) == 1
            assert parent_from_db.children[0].name == "Child Topic"

            # Cleanup
            await db.delete(child)
            await db.delete(parent)
            await db.commit()

    async def test_topic_unique_name(self):
        """Test that topic names must be unique."""
        async with async_session() as db:
            # Create first topic
            topic1 = Topic(name="Unique Topic Name")
            db.add(topic1)
            await db.commit()

            # Try to create duplicate
            topic2 = Topic(name="Unique Topic Name")
            db.add(topic2)

            with pytest.raises(IntegrityError):
                await db.commit()

            await db.rollback()

            # Cleanup
            await db.delete(topic1)
            await db.commit()


@pytest.mark.asyncio
class TestCollectionModel:
    """Test Collection model and user ownership."""

    async def test_create_collection(self):
        """Test creating a collection."""
        async with async_session() as db:
            # Get or create a test user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()

            if not user:
                # Create a test user if none exists
                role_result = await db.execute(select(Role).where(Role.name == "user"))
                role = role_result.scalar_one_or_none()
                if not role:
                    role = Role(name="user", description="Test role")
                    db.add(role)
                    await db.commit()
                    await db.refresh(role)

                user = User(
                    id="test-collection-user-123",
                    email="testcollection@example.com",
                    name="Test Collection User",
                    preferred_username="testcollectionuser",
                    role_id=role.id
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            # Create collection
            collection = Collection(
                name="My Test Collection",
                description="A collection for testing",
                collection_type="book",
                user_id=user.id,
                is_public=False
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)

            assert collection.id is not None
            assert collection.name == "My Test Collection"
            assert collection.collection_type == "book"
            assert collection.user_id == user.id
            assert collection.is_public is False

            # Cleanup
            await db.delete(collection)
            await db.commit()

    async def test_collection_user_relationship(self):
        """Test collection belongs to user."""
        async with async_session() as db:
            # Get existing user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one()

            # Create collection
            collection = Collection(
                name="User Collection Test",
                user_id=user.id,
                collection_type="course"
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)

            # Test relationship
            result = await db.execute(
                select(Collection).where(Collection.id == collection.id)
            )
            coll_from_db = result.scalar_one()
            assert coll_from_db.user.id == user.id

            # Cleanup
            await db.delete(collection)
            await db.commit()


@pytest.mark.asyncio
class TestJobTopicModel:
    """Test JobTopic junction table."""

    async def test_create_job_topic(self):
        """Test creating a job-topic association."""
        async with async_session() as db:
            # Create topic
            topic = Topic(name="Test Job Topic Category")
            db.add(topic)
            await db.commit()
            await db.refresh(topic)

            # Get or create a job
            result = await db.execute(select(Job).limit(1))
            job = result.scalar_one_or_none()

            if not job:
                # Create a test job if none exists
                result = await db.execute(select(User).limit(1))
                user = result.scalar_one()

                job = Job(
                    user_id=user.id,
                    filename="test_job_topic.mp3",
                    file_path="/tmp/test_job_topic.mp3",
                    status="completed"
                )
                db.add(job)
                await db.commit()
                await db.refresh(job)

            # Create job-topic association with AI confidence
            job_topic = JobTopic(
                job_id=job.id,
                topic_id=topic.id,
                ai_confidence=0.85,
                ai_reasoning="Content discusses religious themes",
                user_reviewed=False
            )
            db.add(job_topic)
            await db.commit()
            await db.refresh(job_topic)

            assert job_topic.id is not None
            assert job_topic.ai_confidence == 0.85
            assert job_topic.ai_reasoning is not None
            assert job_topic.user_reviewed is False
            assert job_topic.assigned_by is None  # AI-assigned

            # Cleanup
            await db.delete(job_topic)
            await db.delete(topic)
            await db.commit()

    async def test_job_topic_unique_constraint(self):
        """Test that job-topic pairs must be unique."""
        async with async_session() as db:
            # Create topic and job
            topic = Topic(name="Unique Constraint Topic")
            db.add(topic)
            await db.commit()
            await db.refresh(topic)

            result = await db.execute(select(Job).limit(1))
            job = result.scalar_one()

            # Create first association
            job_topic1 = JobTopic(job_id=job.id, topic_id=topic.id)
            db.add(job_topic1)
            await db.commit()

            # Try to create duplicate
            job_topic2 = JobTopic(job_id=job.id, topic_id=topic.id)
            db.add(job_topic2)

            with pytest.raises(IntegrityError):
                await db.commit()

            await db.rollback()

            # Cleanup
            await db.delete(job_topic1)
            await db.delete(topic)
            await db.commit()

    async def test_job_topic_cascade_delete(self):
        """Test that deleting a job removes its topic associations."""
        async with async_session() as db:
            # Get user and create job
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one()

            job = Job(
                user_id=user.id,
                filename="cascade_test.mp3",
                file_path="/tmp/cascade_test.mp3",
                status="pending"
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            # Create topic
            topic = Topic(name="Cascade Test Topic")
            db.add(topic)
            await db.commit()
            await db.refresh(topic)

            # Create association
            job_topic = JobTopic(job_id=job.id, topic_id=topic.id)
            db.add(job_topic)
            await db.commit()
            job_topic_id = job_topic.id

            # Delete job (should cascade to job_topic)
            await db.delete(job)
            await db.commit()

            # Verify job_topic was deleted
            result = await db.execute(
                select(JobTopic).where(JobTopic.id == job_topic_id)
            )
            deleted_job_topic = result.scalar_one_or_none()
            assert deleted_job_topic is None

            # Cleanup
            await db.delete(topic)
            await db.commit()


@pytest.mark.asyncio
class TestJobCollectionModel:
    """Test JobCollection junction table with position ordering."""

    async def test_create_job_collection(self):
        """Test creating a job-collection association with position."""
        async with async_session() as db:
            # Get user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one()

            # Create collection
            collection = Collection(
                name="Position Test Collection",
                user_id=user.id,
                collection_type="book"
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)

            # Get job
            result = await db.execute(select(Job).limit(1))
            job = result.scalar_one()

            # Create association with position
            job_collection = JobCollection(
                job_id=job.id,
                collection_id=collection.id,
                position=1,
                assigned_by=user.id
            )
            db.add(job_collection)
            await db.commit()
            await db.refresh(job_collection)

            assert job_collection.id is not None
            assert job_collection.position == 1
            assert job_collection.assigned_by == user.id

            # Cleanup
            await db.delete(job_collection)
            await db.delete(collection)
            await db.commit()

    async def test_job_collection_ordering(self):
        """Test that multiple jobs can be ordered within a collection."""
        async with async_session() as db:
            # Get user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one()

            # Create collection
            collection = Collection(
                name="Ordered Collection",
                user_id=user.id,
                collection_type="course"
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)

            # Get multiple jobs
            result = await db.execute(select(Job).limit(3))
            jobs = result.scalars().all()

            if len(jobs) < 3:
                pytest.skip("Need at least 3 jobs for ordering test")

            # Create associations with different positions
            job_collections = []
            for i, job in enumerate(jobs[:3]):
                jc = JobCollection(
                    job_id=job.id,
                    collection_id=collection.id,
                    position=i + 1
                )
                db.add(jc)
                job_collections.append(jc)

            await db.commit()

            # Verify ordering
            result = await db.execute(
                select(JobCollection)
                .where(JobCollection.collection_id == collection.id)
                .order_by(JobCollection.position)
            )
            ordered_jcs = result.scalars().all()

            assert len(ordered_jcs) == 3
            assert ordered_jcs[0].position == 1
            assert ordered_jcs[1].position == 2
            assert ordered_jcs[2].position == 3

            # Cleanup
            for jc in job_collections:
                await db.delete(jc)
            await db.delete(collection)
            await db.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
