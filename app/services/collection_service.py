"""
Collection Service - Business logic for collection management
"""
import logging
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.data.models import Collection, TranscriptionCollection, Transcription
from app.schemas.collections import CollectionCreate, CollectionUpdate, TranscriptionInCollection

logger = logging.getLogger(__name__)



class CollectionService:
    """Service for managing collections"""

    @staticmethod
    async def get_user_collections(
        db: AsyncSession,
        user_id: str,
        collection_type: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> List[Collection]:
        """
        Get all collections for a user with optional filtering
        """
        query = select(Collection).where(Collection.user_id == user_id)

        if collection_type:
            query = query.where(Collection.collection_type == collection_type)

        if is_public is not None:
            query = query.where(Collection.is_public == is_public)

        query = query.order_by(Collection.created_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_collection_by_id(
        db: AsyncSession,
        collection_id: int,
        load_jobs: bool = False
    ) -> Optional[Collection]:
        """Get a collection by ID with optional job loading"""
        query = select(Collection).where(Collection.id == collection_id)

        if load_jobs:
            query = query.options(selectinload(Collection.job_collections))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_collection_job_count(db: AsyncSession, collection_id: int) -> int:
        """Get count of jobs in a collection"""
        result = await db.execute(
            select(func.count(TranscriptionCollection.id))
            .where(TranscriptionCollection.collection_id == collection_id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_collection_transcriptions(
        db: AsyncSession,
        collection_id: int
    ) -> List[TranscriptionInCollection]:
        """Get all transcriptions in a collection with position ordering"""
        result = await db.execute(
            select(TranscriptionCollection, Transcription)
            .join(Transcription, TranscriptionCollection.transcription_id == Transcription.id)
            .where(TranscriptionCollection.collection_id == collection_id)
            .order_by(TranscriptionCollection.position, TranscriptionCollection.created_at)
        )

        transcriptions = []
        for transcription_collection, transcription in result:
            transcriptions.append(TranscriptionInCollection(
                transcription_id=transcription.id,
                position=transcription_collection.position,
                language=transcription.language,
                created_at=transcription_collection.created_at
            ))

        return transcriptions

    @staticmethod
    async def create_collection(
        db: AsyncSession,
        user_id: str,
        collection_data: CollectionCreate
    ) -> Collection:
        """Create a new collection"""
        logger.info(f"Creating collection for user {user_id}: {collection_data.name}")

        collection = Collection(
            name=collection_data.name,
            description=collection_data.description,
            collection_type=collection_data.collection_type,
            user_id=user_id,
            is_public=collection_data.is_public
        )
        db.add(collection)
        await db.commit()
        await db.refresh(collection)

        logger.info(f"Created collection {collection.id}: {collection.name}")
        return collection

    @staticmethod
    async def update_collection(
        db: AsyncSession,
        collection_id: int,
        user_id: str,
        collection_data: CollectionUpdate
    ) -> Collection:
        """Update an existing collection"""
        logger.info(f"Updating collection {collection_id}")

        # Get collection
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        # Check ownership
        if collection.user_id != user_id:
            raise PermissionError("You do not have permission to update this collection")

        # Update fields
        if collection_data.name is not None:
            collection.name = collection_data.name

        if collection_data.description is not None:
            collection.description = collection_data.description

        if collection_data.collection_type is not None:
            collection.collection_type = collection_data.collection_type

        if collection_data.is_public is not None:
            collection.is_public = collection_data.is_public

        await db.commit()
        await db.refresh(collection)

        logger.info(f"Updated collection {collection_id}")
        return collection

    @staticmethod
    async def delete_collection(
        db: AsyncSession,
        collection_id: int,
        user_id: str
    ) -> bool:
        """Delete a collection"""
        logger.info(f"Deleting collection {collection_id}")

        # Get collection
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        # Check ownership
        if collection.user_id != user_id:
            raise PermissionError("You do not have permission to delete this collection")

        # Delete collection (cascade will remove job_collections associations)
        await db.delete(collection)
        await db.commit()

        logger.info(f"Deleted collection {collection_id}")
        return True

    @staticmethod
    async def can_access_collection(
        db: AsyncSession,
        collection_id: int,
        user_id: str
    ) -> bool:
        """Check if user can access a collection (owns it or it's public)"""
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            return False

        return collection.user_id == user_id or collection.is_public

    @staticmethod
    async def add_transcription_to_collection(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str,
        position: Optional[int] = None
    ) -> TranscriptionCollection:
        """Add a transcription to a collection"""
        logger.info(f"Adding transcription {transcription_id} to collection {collection_id}")

        # Verify collection exists and user owns it
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        if collection.user_id != user_id:
            raise PermissionError("You do not have permission to modify this collection")

        # Verify transcription exists and user owns it
        transcription = await db.get(Transcription, transcription_id)
        if not transcription:
            raise ValueError(f"Transcription {transcription_id} not found")

        if transcription.user_id != user_id:
            raise PermissionError("You do not have permission to add this transcription")

        # Check if already in collection
        existing = await db.execute(
            select(TranscriptionCollection)
            .where(
                TranscriptionCollection.transcription_id == transcription_id,
                TranscriptionCollection.collection_id == collection_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Transcription {transcription_id} is already in collection {collection_id}")

        # Auto-assign position if not provided
        if position is None:
            # Get max position
            result = await db.execute(
                select(func.max(TranscriptionCollection.position))
                .where(TranscriptionCollection.collection_id == collection_id)
            )
            max_position = result.scalar_one()
            position = (max_position or 0) + 1

        # Create association
        transcription_collection = TranscriptionCollection(
            transcription_id=transcription_id,
            collection_id=collection_id,
            position=position,
            assigned_by=user_id
        )
        db.add(transcription_collection)
        await db.commit()
        await db.refresh(transcription_collection)

        logger.info(f"Added transcription {transcription_id} to collection {collection_id} at position {position}")
        return transcription_collection

    @staticmethod
    async def remove_transcription_from_collection(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str
    ) -> bool:
        """Remove a transcription from a collection"""
        logger.info(f"Removing transcription {transcription_id} from collection {collection_id}")

        # Verify collection ownership
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        if collection.user_id != user_id:
            raise PermissionError("You do not have permission to modify this collection")

        # Get association
        result = await db.execute(
            select(TranscriptionCollection)
            .where(
                TranscriptionCollection.transcription_id == transcription_id,
                TranscriptionCollection.collection_id == collection_id
            )
        )
        transcription_collection = result.scalar_one_or_none()
        if not transcription_collection:
            raise ValueError(f"Transcription {transcription_id} is not in collection {collection_id}")

        # Delete association
        await db.delete(transcription_collection)
        await db.commit()

        logger.info(f"Removed transcription {transcription_id} from collection {collection_id}")
        return True

    @staticmethod
    async def update_transcription_position(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str,
        new_position: int
    ) -> TranscriptionCollection:
        """Update transcription position within a collection"""
        logger.info(f"Updating position of transcription {transcription_id} in collection {collection_id} to {new_position}")

        # Verify collection ownership
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        if collection.user_id != user_id:
            raise PermissionError("You do not have permission to modify this collection")

        # Get association
        result = await db.execute(
            select(TranscriptionCollection)
            .where(
                TranscriptionCollection.transcription_id == transcription_id,
                TranscriptionCollection.collection_id == collection_id
            )
        )
        transcription_collection = result.scalar_one_or_none()
        if not transcription_collection:
            raise ValueError(f"Transcription {transcription_id} is not in collection {collection_id}")

        # Update position
        transcription_collection.position = new_position
        await db.commit()
        await db.refresh(transcription_collection)

        logger.info(f"Updated position to {new_position}")
        return transcription_collection
