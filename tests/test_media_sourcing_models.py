"""
Unit tests for media sourcing models (AudioFile, Transcription, etc.)
"""
import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.data.models import (
    Base, User, Role, AudioFile, Transcription, TranscriptionChunk,
    TranscriptionTopic, TranscriptionCollection, Collection, Topic
)
from app.config import settings


# Test database URL (same as configured)
TEST_DATABASE_URL = settings.database_url


@pytest.fixture
async def async_session():
    """Create async session for tests"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user"""
    # Create role if doesn't exist
    result = await async_session.execute(select(Role).where(Role.id == 2))
    role = result.scalar_one_or_none()

    if not role:
        role = Role(id=2, name="user", description="Standard user")
        async_session.add(role)
        await async_session.commit()

    # Create test user
    user = User(
        id="test_user_media_sourcing",
        email="test_media@example.com",
        name="Test Media User",
        role_id=2
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    yield user

    # Cleanup
    await async_session.delete(user)
    await async_session.commit()


@pytest.mark.asyncio
async def test_audio_file_creation(async_session: AsyncSession, test_user: User):
    """Test creating an audio file record"""
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/abc123_test.mp3",
        original_filename="test.mp3",
        file_size=1024 * 1024,  # 1MB
        mime_type="audio/mpeg",
        duration=60.5,
        checksum="abc123def456",
        source_type="upload",
    )

    async_session.add(audio_file)
    await async_session.commit()
    await async_session.refresh(audio_file)

    assert audio_file.id is not None
    assert audio_file.user_id == test_user.id
    assert audio_file.source_type == "upload"
    assert audio_file.checksum == "abc123def456"
    assert audio_file.created_at is not None

    # Cleanup
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_audio_file_with_download_source(async_session: AsyncSession, test_user: User):
    """Test creating an audio file from download"""
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/xyz789_youtube.mp3",
        original_filename="Cool Video.mp3",
        file_size=5 * 1024 * 1024,  # 5MB
        mime_type="audio/mpeg",
        duration=180.0,
        checksum="xyz789",
        source_type="download",
        source_url="https://www.youtube.com/watch?v=test123",
        source_platform="youtube"
    )

    async_session.add(audio_file)
    await async_session.commit()
    await async_session.refresh(audio_file)

    assert audio_file.source_type == "download"
    assert audio_file.source_url == "https://www.youtube.com/watch?v=test123"
    assert audio_file.source_platform == "youtube"

    # Cleanup
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_checksum_uniqueness(async_session: AsyncSession, test_user: User):
    """Test that checksum uniqueness constraint works per user"""
    # Create first audio file
    audio_file1 = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/dup123_file1.mp3",
        original_filename="file1.mp3",
        file_size=1024,
        checksum="duplicate_checksum",
        source_type="upload",
    )
    async_session.add(audio_file1)
    await async_session.commit()

    # Try to create second audio file with same checksum for same user
    audio_file2 = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/dup123_file2.mp3",
        original_filename="file2.mp3",
        file_size=1024,
        checksum="duplicate_checksum",
        source_type="upload",
    )
    async_session.add(audio_file2)

    # Should raise integrity error
    with pytest.raises(Exception):  # IntegrityError
        await async_session.commit()

    await async_session.rollback()

    # Cleanup
    await async_session.delete(audio_file1)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_creation(async_session: AsyncSession, test_user: User):
    """Test creating a transcription record"""
    # Create audio file first
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/trans123_test.mp3",
        original_filename="test.mp3",
        file_size=1024,
        checksum="trans123",
        source_type="upload",
    )
    async_session.add(audio_file)
    await async_session.commit()
    await async_session.refresh(audio_file)

    # Create transcription
    transcription = Transcription(
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        transcript="This is a test transcript.",
        language="en",
        model_name="whisper-large-v3",
        avg_confidence=0.95,
        processing_time=12.5,
        status="completed"
    )
    async_session.add(transcription)
    await async_session.commit()
    await async_session.refresh(transcription)

    assert transcription.id is not None
    assert transcription.audio_file_id == audio_file.id
    assert transcription.status == "completed"
    assert transcription.avg_confidence == 0.95

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_chunks(async_session: AsyncSession, test_user: User):
    """Test creating transcription chunks"""
    # Create audio file and transcription
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/chunk123_test.mp3",
        original_filename="test.mp3",
        file_size=1024,
        checksum="chunk123",
        source_type="upload",
    )
    async_session.add(audio_file)
    await async_session.commit()

    transcription = Transcription(
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        transcript="Full transcript text here.",
        status="completed"
    )
    async_session.add(transcription)
    await async_session.commit()
    await async_session.refresh(transcription)

    # Create chunks
    chunk1 = TranscriptionChunk(
        transcription_id=transcription.id,
        chunk_index=0,
        text="First chunk of text.",
        start_time=0.0,
        end_time=5.0,
        start_char_pos=0,
        end_char_pos=20
    )
    chunk2 = TranscriptionChunk(
        transcription_id=transcription.id,
        chunk_index=1,
        text="Second chunk of text.",
        start_time=5.0,
        end_time=10.0,
        start_char_pos=20,
        end_char_pos=41
    )
    async_session.add_all([chunk1, chunk2])
    await async_session.commit()

    # Verify chunks
    result = await async_session.execute(
        select(TranscriptionChunk)
        .where(TranscriptionChunk.transcription_id == transcription.id)
        .order_by(TranscriptionChunk.chunk_index)
    )
    chunks = result.scalars().all()

    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1
    assert chunks[0].text == "First chunk of text."

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_cascade_delete_audio_file(async_session: AsyncSession, test_user: User):
    """Test that deleting audio file cascades to transcriptions"""
    # Create audio file
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/cascade123_test.mp3",
        original_filename="test.mp3",
        file_size=1024,
        checksum="cascade123",
        source_type="upload",
    )
    async_session.add(audio_file)
    await async_session.commit()
    await async_session.refresh(audio_file)

    # Create transcription
    transcription = Transcription(
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        transcript="Test transcript",
        status="completed"
    )
    async_session.add(transcription)
    await async_session.commit()
    transcription_id = transcription.id

    # Delete audio file
    await async_session.delete(audio_file)
    await async_session.commit()

    # Verify transcription was also deleted (cascade)
    result = await async_session.execute(
        select(Transcription).where(Transcription.id == transcription_id)
    )
    deleted_transcription = result.scalar_one_or_none()

    assert deleted_transcription is None


@pytest.mark.asyncio
async def test_transcription_topics_assignment(async_session: AsyncSession, test_user: User):
    """Test assigning topics to transcriptions"""
    # Create topic
    topic = Topic(name="Test Topic Media Sourcing", description="Test topic for media sourcing")
    async_session.add(topic)
    await async_session.commit()
    await async_session.refresh(topic)

    # Create audio file and transcription
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/topic123_test.mp3",
        original_filename="test.mp3",
        file_size=1024,
        checksum="topic123",
        source_type="upload",
    )
    async_session.add(audio_file)
    await async_session.commit()

    transcription = Transcription(
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        transcript="Test transcript",
        status="completed"
    )
    async_session.add(transcription)
    await async_session.commit()
    await async_session.refresh(transcription)

    # Assign topic
    transcription_topic = TranscriptionTopic(
        transcription_id=transcription.id,
        topic_id=topic.id,
        ai_confidence=0.85,
        ai_reasoning="AI detected this topic",
        user_reviewed=False
    )
    async_session.add(transcription_topic)
    await async_session.commit()

    # Verify assignment
    result = await async_session.execute(
        select(TranscriptionTopic)
        .where(TranscriptionTopic.transcription_id == transcription.id)
    )
    assignments = result.scalars().all()

    assert len(assignments) == 1
    assert assignments[0].topic_id == topic.id
    assert assignments[0].ai_confidence == 0.85

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.delete(topic)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_collections_assignment(async_session: AsyncSession, test_user: User):
    """Test adding transcriptions to collections"""
    # Create collection
    collection = Collection(
        name="Test Collection Media Sourcing",
        user_id=test_user.id,
        collection_type="playlist"
    )
    async_session.add(collection)
    await async_session.commit()
    await async_session.refresh(collection)

    # Create audio file and transcription
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/user_test/2025/10/coll123_test.mp3",
        original_filename="test.mp3",
        file_size=1024,
        checksum="coll123",
        source_type="upload",
    )
    async_session.add(audio_file)
    await async_session.commit()

    transcription = Transcription(
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        transcript="Test transcript",
        status="completed"
    )
    async_session.add(transcription)
    await async_session.commit()
    await async_session.refresh(transcription)

    # Add to collection with position
    transcription_collection = TranscriptionCollection(
        transcription_id=transcription.id,
        collection_id=collection.id,
        position=1,
        assigned_by=test_user.id
    )
    async_session.add(transcription_collection)
    await async_session.commit()

    # Verify assignment
    result = await async_session.execute(
        select(TranscriptionCollection)
        .where(TranscriptionCollection.transcription_id == transcription.id)
    )
    assignments = result.scalars().all()

    assert len(assignments) == 1
    assert assignments[0].collection_id == collection.id
    assert assignments[0].position == 1

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.delete(collection)
    await async_session.commit()
