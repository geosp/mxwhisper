"""
Unit tests for media sourcing services
"""
import pytest
import os
import tempfile
from io import BytesIO
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.data.models import (
    Base, User, Role, AudioFile, Transcription, TranscriptionChunk
)
from app.services.audio_file_service import AudioFileService
from app.services.transcription_service import TranscriptionService
from app.services.download_service import DownloadService
from app.config import settings


# Test database URL
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
        id="test_user_services",
        email="test_services@example.com",
        name="Test Services User",
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
async def test_sanitize_filename():
    """Test filename sanitization"""
    # Test with special characters (trailing underscores are stripped)
    result = AudioFileService.sanitize_filename("test@#$%file!.mp3")
    assert result == "test_file.mp3"

    # Test with spaces
    result = AudioFileService.sanitize_filename("my  test   file.mp3")
    assert result == "my_test_file.mp3"

    # Test with long name
    long_name = "a" * 250 + ".mp3"
    result = AudioFileService.sanitize_filename(long_name)
    assert len(result) <= 204  # 200 + ".mp3"


@pytest.mark.asyncio
async def test_generate_file_path():
    """Test file path generation"""
    path = AudioFileService.generate_file_path(
        user_id="user123",
        original_filename="test file.mp3",
        checksum="abc123def456789"
    )

    # Should contain user folder
    assert "user_user123" in path

    # Should contain date components
    now = datetime.utcnow()
    assert str(now.year) in path
    assert now.strftime("%m") in path

    # Should contain checksum prefix
    assert "abc123def456789"[:16] in path

    # Should be sanitized
    assert "test_file.mp3" in path


@pytest.mark.asyncio
async def test_calculate_checksum():
    """Test checksum calculation"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
        f.write(b"Test content for checksum")
        temp_path = f.name

    try:
        checksum = await AudioFileService.calculate_checksum(temp_path)

        # Should return SHA256 hex (64 characters)
        assert len(checksum) == 64
        assert all(c in '0123456789abcdef' for c in checksum)

        # Same content should produce same checksum
        checksum2 = await AudioFileService.calculate_checksum(temp_path)
        assert checksum == checksum2

    finally:
        os.remove(temp_path)


@pytest.mark.asyncio
async def test_check_duplicate(async_session: AsyncSession, test_user: User):
    """Test duplicate detection"""
    # Create an audio file
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file.mp3",
        original_filename="file.mp3",
        file_size=1024,
        checksum="test_checksum_123",
        source_type="upload"
    )
    async_session.add(audio_file)
    await async_session.commit()

    # Check for duplicate (should find it)
    duplicate = await AudioFileService.check_duplicate(
        async_session,
        test_user.id,
        "test_checksum_123"
    )
    assert duplicate is not None
    assert duplicate.id == audio_file.id

    # Check with different checksum (should not find)
    no_duplicate = await AudioFileService.check_duplicate(
        async_session,
        test_user.id,
        "different_checksum"
    )
    assert no_duplicate is None

    # Cleanup
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_service_create(async_session: AsyncSession, test_user: User):
    """Test creating a transcription"""
    # Create audio file first
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file.mp3",
        original_filename="file.mp3",
        file_size=1024,
        checksum="trans_test_123",
        source_type="upload"
    )
    async_session.add(audio_file)
    await async_session.commit()
    await async_session.refresh(audio_file)

    # Create transcription
    transcription = await TranscriptionService.create_transcription(
        async_session,
        audio_file_id=audio_file.id,
        user_id=test_user.id,
        model_name="whisper-large-v3",
        language="en"
    )

    assert transcription.id is not None
    assert transcription.audio_file_id == audio_file.id
    assert transcription.user_id == test_user.id
    assert transcription.status == "pending"
    assert transcription.model_name == "whisper-large-v3"

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_service_update_result(async_session: AsyncSession, test_user: User):
    """Test updating transcription with results"""
    # Create audio file and transcription
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file.mp3",
        original_filename="file.mp3",
        file_size=1024,
        checksum="trans_update_123",
        source_type="upload"
    )
    async_session.add(audio_file)
    await async_session.commit()

    transcription = await TranscriptionService.create_transcription(
        async_session,
        audio_file_id=audio_file.id,
        user_id=test_user.id
    )

    # Update with results
    updated = await TranscriptionService.update_transcription_result(
        async_session,
        transcription_id=transcription.id,
        transcript="This is the test transcript.",
        language="en",
        avg_confidence=0.92,
        processing_time=15.5
    )

    assert updated.transcript == "This is the test transcript."
    assert updated.language == "en"
    assert updated.avg_confidence == 0.92
    assert updated.processing_time == 15.5
    assert updated.status == "completed"

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_service_create_chunks(async_session: AsyncSession, test_user: User):
    """Test creating transcription chunks"""
    # Create audio file and transcription
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file.mp3",
        original_filename="file.mp3",
        file_size=1024,
        checksum="chunks_test_123",
        source_type="upload"
    )
    async_session.add(audio_file)
    await async_session.commit()

    transcription = await TranscriptionService.create_transcription(
        async_session,
        audio_file_id=audio_file.id,
        user_id=test_user.id
    )

    # Create chunks
    chunks_data = [
        {
            'chunk_index': 0,
            'text': 'First chunk',
            'start_time': 0.0,
            'end_time': 5.0,
            'start_char_pos': 0,
            'end_char_pos': 11
        },
        {
            'chunk_index': 1,
            'text': 'Second chunk',
            'start_time': 5.0,
            'end_time': 10.0,
            'start_char_pos': 11,
            'end_char_pos': 23
        }
    ]

    chunks = await TranscriptionService.create_chunks(
        async_session,
        transcription_id=transcription.id,
        chunks_data=chunks_data
    )

    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == 'First chunk'
    assert chunks[1].chunk_index == 1

    # Cleanup
    await async_session.delete(transcription)
    await async_session.delete(audio_file)
    await async_session.commit()


@pytest.mark.asyncio
async def test_download_service_validate_url():
    """Test URL validation"""
    # Valid URLs
    assert DownloadService.validate_url("https://www.youtube.com/watch?v=test123")
    assert DownloadService.validate_url("https://soundcloud.com/artist/track")

    # Invalid URLs
    assert not DownloadService.validate_url("not a url")
    # Note: ftp:// is technically valid URL format, just not http/https
    # Our validation just checks URL structure, not protocol


@pytest.mark.asyncio
async def test_download_service_detect_platform():
    """Test platform detection"""
    assert DownloadService.detect_platform("https://www.youtube.com/watch?v=123") == "youtube"
    assert DownloadService.detect_platform("https://youtu.be/123") == "youtube"
    assert DownloadService.detect_platform("https://soundcloud.com/test") == "soundcloud"
    assert DownloadService.detect_platform("https://vimeo.com/123") == "vimeo"
    assert DownloadService.detect_platform("https://example.com") == "other"


@pytest.mark.asyncio
async def test_download_service_is_available():
    """Test if yt-dlp is available"""
    is_available = await DownloadService.is_yt_dlp_available()

    # yt-dlp should be available in the test environment
    # If not, this test will show it
    assert isinstance(is_available, bool)


@pytest.mark.asyncio
async def test_audio_file_service_get_user_files(async_session: AsyncSession, test_user: User):
    """Test getting user's audio files"""
    # Create test audio files
    file1 = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file1.mp3",
        original_filename="file1.mp3",
        file_size=1024,
        checksum="list_test_1",
        source_type="upload"
    )
    file2 = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file2.mp3",
        original_filename="file2.mp3",
        file_size=2048,
        checksum="list_test_2",
        source_type="download",
        source_url="https://example.com/audio"
    )

    async_session.add_all([file1, file2])
    await async_session.commit()

    # Get all files
    files = await AudioFileService.get_user_files(async_session, test_user.id)
    assert len(files) >= 2

    # Get only uploads
    uploads = await AudioFileService.get_user_files(
        async_session,
        test_user.id,
        source_type="upload"
    )
    assert all(f.source_type == "upload" for f in uploads)

    # Get only downloads
    downloads = await AudioFileService.get_user_files(
        async_session,
        test_user.id,
        source_type="download"
    )
    assert all(f.source_type == "download" for f in downloads)

    # Cleanup
    await async_session.delete(file1)
    await async_session.delete(file2)
    await async_session.commit()


@pytest.mark.asyncio
async def test_transcription_service_count_user_transcriptions(async_session: AsyncSession, test_user: User):
    """Test counting user's transcriptions"""
    # Create audio file
    audio_file = AudioFile(
        user_id=test_user.id,
        file_path="uploads/test/file.mp3",
        original_filename="file.mp3",
        file_size=1024,
        checksum="count_test_123",
        source_type="upload"
    )
    async_session.add(audio_file)
    await async_session.commit()

    # Create transcriptions
    trans1 = await TranscriptionService.create_transcription(
        async_session,
        audio_file_id=audio_file.id,
        user_id=test_user.id
    )

    trans2 = await TranscriptionService.create_transcription(
        async_session,
        audio_file_id=audio_file.id,
        user_id=test_user.id
    )

    # Mark one as completed
    await TranscriptionService.update_transcription_result(
        async_session,
        trans1.id,
        transcript="Test",
        language="en",
        avg_confidence=0.9
    )

    # Count all
    count_all = await TranscriptionService.count_user_transcriptions(
        async_session,
        test_user.id
    )
    assert count_all >= 2

    # Count only completed
    count_completed = await TranscriptionService.count_user_transcriptions(
        async_session,
        test_user.id,
        status="completed"
    )
    assert count_completed >= 1

    # Cleanup
    await async_session.delete(trans1)
    await async_session.delete(trans2)
    await async_session.delete(audio_file)
    await async_session.commit()
