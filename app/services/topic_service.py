"""
Topic Service - Business logic for topic management
"""
import logging
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.models import Topic
from app.schemas.topics import TopicCreate, TopicUpdate, TopicWithChildren

logger = logging.getLogger(__name__)


class TopicService:
    """Service for managing topics"""

    @staticmethod
    async def get_all_topics(db: AsyncSession) -> List[Topic]:
        """Get all topics from database"""
        result = await db.execute(
            select(Topic).order_by(Topic.parent_id, Topic.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def build_topic_hierarchy(topics: List[Topic]) -> List[TopicWithChildren]:
        """
        Build hierarchical topic structure from flat list
        Returns list of root topics with nested children
        """
        # Create a mapping of topic ID to topic with children
        topic_map = {}
        for topic in topics:
            topic_dict = {
                "id": topic.id,
                "name": topic.name,
                "description": topic.description,
                "parent_id": topic.parent_id,
                "created_at": topic.created_at,
                "updated_at": topic.updated_at,
                "children": []
            }
            topic_map[topic.id] = topic_dict

        # Build hierarchy
        root_topics = []
        for topic in topics:
            topic_dict = topic_map[topic.id]
            if topic.parent_id is None:
                root_topics.append(TopicWithChildren(**topic_dict))
            else:
                # Add to parent's children
                if topic.parent_id in topic_map:
                    topic_map[topic.parent_id]["children"].append(
                        TopicWithChildren(**topic_dict)
                    )

        return root_topics

    @staticmethod
    async def get_topic_by_id(db: AsyncSession, topic_id: int) -> Optional[Topic]:
        """Get a topic by ID"""
        result = await db.execute(
            select(Topic).where(Topic.id == topic_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_topic_by_name(db: AsyncSession, name: str) -> Optional[Topic]:
        """Get a topic by name"""
        result = await db.execute(
            select(Topic).where(Topic.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_topic(
        db: AsyncSession,
        topic_data: TopicCreate
    ) -> Topic:
        """Create a new topic"""
        logger.info(f"Creating topic: {topic_data.name}")

        # Check if name already exists
        existing = await TopicService.get_topic_by_name(db, topic_data.name)
        if existing:
            raise ValueError(f"Topic with name '{topic_data.name}' already exists")

        # Validate parent exists if provided
        if topic_data.parent_id:
            parent = await TopicService.get_topic_by_id(db, topic_data.parent_id)
            if not parent:
                raise ValueError(f"Parent topic {topic_data.parent_id} not found")

        # Create topic
        topic = Topic(
            name=topic_data.name,
            description=topic_data.description,
            parent_id=topic_data.parent_id
        )
        db.add(topic)
        await db.commit()
        await db.refresh(topic)

        logger.info(f"Created topic {topic.id}: {topic.name}")
        return topic

    @staticmethod
    async def update_topic(
        db: AsyncSession,
        topic_id: int,
        topic_data: TopicUpdate
    ) -> Topic:
        """Update an existing topic"""
        logger.info(f"Updating topic {topic_id}")

        # Get topic
        topic = await TopicService.get_topic_by_id(db, topic_id)
        if not topic:
            raise ValueError(f"Topic {topic_id} not found")

        # Check for name conflicts if name is being updated
        if topic_data.name and topic_data.name != topic.name:
            existing = await TopicService.get_topic_by_name(db, topic_data.name)
            if existing:
                raise ValueError(f"Topic with name '{topic_data.name}' already exists")
            topic.name = topic_data.name

        # Update fields
        if topic_data.description is not None:
            topic.description = topic_data.description

        if topic_data.parent_id is not None:
            # Validate parent exists
            parent = await TopicService.get_topic_by_id(db, topic_data.parent_id)
            if not parent:
                raise ValueError(f"Parent topic {topic_data.parent_id} not found")

            # Prevent circular references
            if topic_data.parent_id == topic_id:
                raise ValueError("Topic cannot be its own parent")

            # Check if new parent would create a cycle
            if await TopicService._would_create_cycle(db, topic_id, topic_data.parent_id):
                raise ValueError("Cannot set parent - would create circular reference")

            topic.parent_id = topic_data.parent_id

        await db.commit()
        await db.refresh(topic)

        logger.info(f"Updated topic {topic_id}")
        return topic

    @staticmethod
    async def delete_topic(db: AsyncSession, topic_id: int) -> bool:
        """
        Delete a topic
        Raises ValueError if topic has children
        """
        logger.info(f"Deleting topic {topic_id}")

        # Get topic
        topic = await TopicService.get_topic_by_id(db, topic_id)
        if not topic:
            raise ValueError(f"Topic {topic_id} not found")

        # Check if topic has children
        result = await db.execute(
            select(Topic).where(Topic.parent_id == topic_id)
        )
        children = result.scalars().all()
        if children:
            raise ValueError(
                f"Cannot delete topic - it has {len(children)} child topics. "
                "Delete or reassign children first."
            )

        # Delete topic (cascade will remove job_topics associations)
        await db.delete(topic)
        await db.commit()

        logger.info(f"Deleted topic {topic_id}")
        return True

    @staticmethod
    async def _would_create_cycle(
        db: AsyncSession,
        topic_id: int,
        new_parent_id: int
    ) -> bool:
        """
        Check if setting new_parent_id as parent of topic_id would create a cycle
        """
        visited = set()
        current_id = new_parent_id

        while current_id is not None:
            if current_id == topic_id:
                return True  # Found a cycle

            if current_id in visited:
                break  # Already checked this path

            visited.add(current_id)

            # Get parent of current topic
            result = await db.execute(
                select(Topic.parent_id).where(Topic.id == current_id)
            )
            current_id = result.scalar_one_or_none()

        return False

    @staticmethod
    async def get_topic_children(db: AsyncSession, topic_id: int) -> List[Topic]:
        """Get all direct children of a topic"""
        result = await db.execute(
            select(Topic).where(Topic.parent_id == topic_id).order_by(Topic.name)
        )
        return list(result.scalars().all())
