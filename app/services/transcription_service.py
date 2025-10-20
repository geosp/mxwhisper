"""
TranscriptionService - Manages transcription domain logic
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import (
    Transcription, TranscriptionChunk, TranscriptionTopic,
    TranscriptionCollection, AudioFile, Topic, Collection
)


class TranscriptionService:
    """Service for managing transcriptions (domain entities separate from job orchestration)"""

    @staticmethod
    async def create_transcription(
        db: AsyncSession,
        audio_file_id: int,
        user_id: str,
        model_name: Optional[str] = None,
        language: Optional[str] = None
    ) -> Transcription:
        """
        Create new transcription record with pending status.

        Args:
            db: Database session
            audio_file_id: ID of the audio file to transcribe
            user_id: User's ID
            model_name: Whisper model name (optional)
            language: Language code (optional)

        Returns:
            Created Transcription record

        Raises:
            ValueError: If audio file doesn't exist or user doesn't own it
        """
        # Verify audio file exists and user owns it
        result = await db.execute(
            select(AudioFile).where(AudioFile.id == audio_file_id)
        )
        audio_file = result.scalar_one_or_none()

        if not audio_file:
            raise ValueError(f"Audio file {audio_file_id} not found")

        if audio_file.user_id != user_id:
            raise ValueError(f"User {user_id} does not own audio file {audio_file_id}")

        # Create transcription with pending status
        transcription = Transcription(
            audio_file_id=audio_file_id,
            user_id=user_id,
            transcript="",  # Will be filled in when processing completes
            model_name=model_name,
            language=language,
            status="pending"
        )

        db.add(transcription)
        await db.commit()
        await db.refresh(transcription)

        return transcription

    @staticmethod
    async def update_transcription_result(
        db: AsyncSession,
        transcription_id: int,
        transcript: str,
        language: str,
        avg_confidence: float,
        segments: Optional[List[Dict[str, Any]]] = None,
        processing_time: Optional[float] = None,
        model_version: Optional[str] = None
    ) -> Transcription:
        """
        Update transcription with results from Whisper.

        Args:
            db: Database session
            transcription_id: Transcription ID
            transcript: Full transcript text
            language: Detected language code
            avg_confidence: Average confidence score
            segments: List of segments with temporal and spatial information (optional)
            processing_time: Time taken to transcribe (seconds)
            model_version: Model version used

        Returns:
            Updated Transcription record

        Raises:
            ValueError: If transcription not found
        """
        transcription = await TranscriptionService.get_by_id(db, transcription_id)

        if not transcription:
            raise ValueError(f"Transcription {transcription_id} not found")

        # Update transcription
        transcription.transcript = transcript
        transcription.language = language
        transcription.avg_confidence = avg_confidence
        if segments is not None:
            transcription.segments = segments
        transcription.processing_time = processing_time
        transcription.model_version = model_version
        transcription.status = "completed"

        await db.commit()
        await db.refresh(transcription)

        return transcription

    @staticmethod
    async def mark_as_failed(
        db: AsyncSession,
        transcription_id: int,
        error_message: str
    ) -> Transcription:
        """
        Mark transcription as failed with error message.

        Args:
            db: Database session
            transcription_id: Transcription ID
            error_message: Error description

        Returns:
            Updated Transcription record
        """
        transcription = await TranscriptionService.get_by_id(db, transcription_id)

        if not transcription:
            raise ValueError(f"Transcription {transcription_id} not found")

        transcription.status = "failed"
        transcription.error_message = error_message

        await db.commit()
        await db.refresh(transcription)

        return transcription

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        transcription_id: int
    ) -> Optional[Transcription]:
        """
        Get transcription by ID.

        Args:
            db: Database session
            transcription_id: Transcription ID

        Returns:
            Transcription or None
        """
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_transcriptions(
        db: AsyncSession,
        user_id: str,
        audio_file_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Transcription]:
        """
        List user's transcriptions with optional filtering.

        Args:
            db: Database session
            user_id: User's ID
            audio_file_id: Filter by audio file (optional)
            status: Filter by status (optional)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of Transcription records
        """
        query = select(Transcription).where(Transcription.user_id == user_id)

        if audio_file_id:
            query = query.where(Transcription.audio_file_id == audio_file_id)

        if status:
            query = query.where(Transcription.status == status)

        query = query.order_by(Transcription.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def count_user_transcriptions(
        db: AsyncSession,
        user_id: str,
        audio_file_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> int:
        """
        Count user's transcriptions.

        Args:
            db: Database session
            user_id: User's ID
            audio_file_id: Filter by audio file (optional)
            status: Filter by status (optional)

        Returns:
            Count of transcriptions
        """
        query = select(func.count(Transcription.id)).where(Transcription.user_id == user_id)

        if audio_file_id:
            query = query.where(Transcription.audio_file_id == audio_file_id)

        if status:
            query = query.where(Transcription.status == status)

        result = await db.execute(query)
        return result.scalar_one()

    @staticmethod
    async def create_chunks(
        db: AsyncSession,
        transcription_id: int,
        chunks_data: List[Dict[str, Any]]
    ) -> List[TranscriptionChunk]:
        """
        Create transcription chunks with temporal and spatial alignment.

        Args:
            db: Database session
            transcription_id: Transcription ID
            chunks_data: List of chunk dictionaries with keys:
                - chunk_index: int
                - text: str
                - start_time: float (optional)
                - end_time: float (optional)
                - start_char_pos: int (optional)
                - end_char_pos: int (optional)
                - embedding: list (optional)
                - topic_summary: str (optional)
                - keywords: list[str] (optional)
                - confidence: float (optional)

        Returns:
            List of created TranscriptionChunk records
        """
        chunks = []

        for chunk_data in chunks_data:
            chunk = TranscriptionChunk(
                transcription_id=transcription_id,
                chunk_index=chunk_data['chunk_index'],
                text=chunk_data['text'],
                start_time=chunk_data.get('start_time'),
                end_time=chunk_data.get('end_time'),
                start_char_pos=chunk_data.get('start_char_pos'),
                end_char_pos=chunk_data.get('end_char_pos'),
                embedding=chunk_data.get('embedding'),
                topic_summary=chunk_data.get('topic_summary'),
                keywords=chunk_data.get('keywords'),
                confidence=chunk_data.get('confidence')
            )
            chunks.append(chunk)

        db.add_all(chunks)
        await db.commit()

        # Refresh all chunks
        for chunk in chunks:
            await db.refresh(chunk)

        return chunks

    @staticmethod
    async def assign_topics(
        db: AsyncSession,
        transcription_id: int,
        topic_ids: List[int],
        user_id: str,
        ai_confidence: Optional[float] = None,
        ai_reasoning: Optional[str] = None
    ) -> List[TranscriptionTopic]:
        """
        Assign topics to transcription.

        Args:
            db: Database session
            transcription_id: Transcription ID
            topic_ids: List of topic IDs to assign
            user_id: User ID (for user-initiated assignments)
            ai_confidence: AI confidence score (for AI assignments)
            ai_reasoning: AI reasoning text (for AI assignments)

        Returns:
            List of TranscriptionTopic records

        Raises:
            ValueError: If transcription or topics don't exist
        """
        # Verify transcription exists
        transcription = await TranscriptionService.get_by_id(db, transcription_id)
        if not transcription:
            raise ValueError(f"Transcription {transcription_id} not found")

        # Verify all topics exist
        result = await db.execute(
            select(Topic).where(Topic.id.in_(topic_ids))
        )
        topics = result.scalars().all()

        if len(topics) != len(topic_ids):
            raise ValueError("One or more topic IDs are invalid")

        # Create assignments
        assignments = []
        for topic_id in topic_ids:
            # Check if assignment already exists
            result = await db.execute(
                select(TranscriptionTopic).where(
                    TranscriptionTopic.transcription_id == transcription_id,
                    TranscriptionTopic.topic_id == topic_id
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                assignment = TranscriptionTopic(
                    transcription_id=transcription_id,
                    topic_id=topic_id,
                    assigned_by=user_id if not ai_confidence else None,
                    ai_confidence=ai_confidence,
                    ai_reasoning=ai_reasoning,
                    user_reviewed=False
                )
                db.add(assignment)
                assignments.append(assignment)

        await db.commit()

        for assignment in assignments:
            await db.refresh(assignment)

        return assignments

    @staticmethod
    async def add_to_collection(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str,
        position: Optional[int] = None
    ) -> TranscriptionCollection:
        """
        Add transcription to collection.

        Args:
            db: Database session
            transcription_id: Transcription ID
            collection_id: Collection ID
            user_id: User ID
            position: Position in collection (optional)

        Returns:
            TranscriptionCollection record

        Raises:
            ValueError: If transcription/collection don't exist or user doesn't own collection
        """
        # Verify transcription exists
        transcription = await TranscriptionService.get_by_id(db, transcription_id)
        if not transcription:
            raise ValueError(f"Transcription {transcription_id} not found")

        # Verify collection exists and user owns it
        result = await db.execute(
            select(Collection).where(Collection.id == collection_id)
        )
        collection = result.scalar_one_or_none()

        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        if collection.user_id != user_id:
            raise ValueError(f"User {user_id} does not own collection {collection_id}")

        # Check if already in collection
        result = await db.execute(
            select(TranscriptionCollection).where(
                TranscriptionCollection.transcription_id == transcription_id,
                TranscriptionCollection.collection_id == collection_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update position if provided
            if position is not None:
                existing.position = position
                await db.commit()
                await db.refresh(existing)
            return existing

        # Create new assignment
        assignment = TranscriptionCollection(
            transcription_id=transcription_id,
            collection_id=collection_id,
            position=position,
            assigned_by=user_id
        )

        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        return assignment

    @staticmethod
    async def remove_from_collection(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str
    ) -> bool:
        """
        Remove transcription from collection.

        Args:
            db: Database session
            transcription_id: Transcription ID
            collection_id: Collection ID
            user_id: User ID (for permission check)

        Returns:
            True if removed, False if not found
        """
        # Verify collection ownership
        result = await db.execute(
            select(Collection).where(Collection.id == collection_id)
        )
        collection = result.scalar_one_or_none()

        if not collection or collection.user_id != user_id:
            return False

        # Find and delete assignment
        result = await db.execute(
            select(TranscriptionCollection).where(
                TranscriptionCollection.transcription_id == transcription_id,
                TranscriptionCollection.collection_id == collection_id
            )
        )
        assignment = result.scalar_one_or_none()

        if assignment:
            await db.delete(assignment)
            await db.commit()
            return True

        return False

    @staticmethod
    async def delete_transcription(
        db: AsyncSession,
        transcription_id: int,
        user_id: str
    ) -> bool:
        """
        Delete transcription (keeps audio file).

        Args:
            db: Database session
            transcription_id: Transcription ID
            user_id: User ID (for permission check)

        Returns:
            True if deleted, False if not found or permission denied
        """
        transcription = await TranscriptionService.get_by_id(db, transcription_id)

        if not transcription:
            return False

        # Permission check
        if transcription.user_id != user_id:
            return False

        # Delete (cascades to chunks, topics, collections)
        await db.delete(transcription)
        await db.commit()

        return True

    @staticmethod
    async def get_chunk_topic_summaries(db: AsyncSession, transcription_id: int) -> List[str]:
        """
        Fetch all topic_summary fields from TranscriptionChunk records for a given transcription.
        Returns a list of non-empty topic summaries.
        """
        result = await db.execute(
            select(TranscriptionChunk.topic_summary)
            .where(
                TranscriptionChunk.transcription_id == transcription_id,
                TranscriptionChunk.topic_summary.isnot(None),
                TranscriptionChunk.topic_summary != ""
            )
        )
        summaries = [row[0] for row in result.fetchall() if row[0]]
        return summaries

    @staticmethod
    async def analyze_topic_summaries_with_llm(summaries: List[str], llm_client, override_prompt: str = None, canonical_topic_names: list = None) -> List[str]:
        """
        Use an LLM to analyze chunk topic summaries and return a list of main topics for the transcription.
        Args:
            summaries: List of chunk topic summaries (strings)
            llm_client: An LLM client instance with an async .complete(prompt) method
            override_prompt: If provided, use this prompt instead of the default
            canonical_topic_names: List of canonical topic names to match against (case-insensitive)
        Returns:
            List of canonical topic names/labels (strings)
        """
        import re
        if not summaries:
            return []
        prompt = override_prompt if override_prompt else (
            "Given the following list of topic summaries from audio chunks, "
            "identify the main topics that best describe the overall content. "
            "Return a comma-separated list of canonical topic names.\n\n"
            "Chunk topic summaries:\n" + "\n".join(f"- {s}" for s in summaries)
        )
        response = await llm_client.complete(prompt)

        # Build regex patterns for each canonical topic (ignore case, allow extra quotes/whitespace)
        patterns = [re.compile(rf"['\"]?{re.escape(name)}['\"]?", re.IGNORECASE) for name in (canonical_topic_names or [])]
        found_topics = set()
        for pat, name in zip(patterns, (canonical_topic_names or [])):
            if pat.search(response):
                found_topics.add(name)

        # If no canonical topics matched, fallback to comma-split and strip quotes/whitespace
        if not found_topics:
            topics = [t.strip().strip('"').strip("'") for t in response.split(",") if t.strip()]
            # Only keep those that match canonical topics (case-insensitive)
            canonical_lower = {n.lower(): n for n in (canonical_topic_names or [])}
            found_topics = set()
            for t in topics:
                key = t.lower()
                if key in canonical_lower:
                    found_topics.add(canonical_lower[key])

        return list(found_topics)

    @staticmethod
    async def map_topics_to_ids(db: AsyncSession, topic_names: List[str]) -> List[int]:
        """
        Map a list of topic names to canonical Topic IDs. If a topic is not found, use the 'Unknown' topic ID.
        Args:
            db: Database session
            topic_names: List of topic names (strings)
        Returns:
            List of topic IDs (ints)
        """
        if not topic_names:
            return []
        # Fetch all topics from the database (name -> id, case-insensitive)
        result = await db.execute(select(Topic.id, Topic.name))
        topic_map = {name.lower(): id for id, name in result.fetchall()}
        # Find the 'unknown' topic id
        unknown_id = topic_map.get("unknown")
        topic_ids = []
        for name in topic_names:
            topic_id = topic_map.get(name.lower(), unknown_id)
            if topic_id is not None:
                topic_ids.append(topic_id)
        return topic_ids

    @staticmethod
    async def assign_topics_to_transcription(
        db: AsyncSession,
        transcription_id: int,
        topic_ids: List[int],
        user_id: str,
        ai_confidence: Optional[float] = None,
        ai_reasoning: Optional[str] = None
    ) -> List[TranscriptionTopic]:
        """
        Assign topics to a transcription using the assign_topics method.
        """
        return await TranscriptionService.assign_topics(
            db=db,
            transcription_id=transcription_id,
            topic_ids=topic_ids,
            user_id=user_id,
            ai_confidence=ai_confidence,
            ai_reasoning=ai_reasoning
        )
