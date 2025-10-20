"""
AudioFileService - Handles audio file storage, deduplication, and metadata extraction
"""
import hashlib
import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import AudioFile
from app.config import settings


class AudioFileService:
    """Service for managing audio files with deduplication and user folder organization"""

    @staticmethod
    async def calculate_checksum(file_path: str) -> str:
        """
        Calculate SHA256 checksum for deduplication.
        Reads file in chunks to handle large files efficiently.

        Args:
            file_path: Path to the file

        Returns:
            SHA256 hex digest
        """
        sha256 = hashlib.sha256()

        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(8192)  # 8KB chunks
                if not chunk:
                    break
                sha256.update(chunk)

        return sha256.hexdigest()

    @staticmethod
    def sanitize_filename(filename: str, max_length: int = 200) -> str:
        """
        Sanitize filename by removing special characters and limiting length.

        Args:
            filename: Original filename
            max_length: Maximum length for the name part (excluding extension)

        Returns:
            Sanitized filename
        """
        # Get name and extension
        name, ext = os.path.splitext(filename)

        # Remove or replace unsafe characters
        # Keep alphanumeric, spaces, hyphens, underscores
        name = re.sub(r'[^\w\s\-]', '_', name)
        # Replace multiple spaces/underscores with single underscore
        name = re.sub(r'[\s_]+', '_', name)
        # Remove leading/trailing underscores
        name = name.strip('_')

        # Truncate if too long
        if len(name) > max_length:
            name = name[:max_length]

        # Ensure extension is clean
        ext = re.sub(r'[^\w\.]', '', ext)

        return f"{name}{ext}" if name else f"file{ext}"

    @staticmethod
    def generate_file_path(user_id: str, original_filename: str, checksum: str) -> str:
        """
        Generate user-specific file path with date-based organization.

        Format: uploads/user_{user_id}/YYYY/MM/{checksum_prefix}_{sanitized_filename}.{ext}

        Args:
            user_id: User's ID
            original_filename: Original uploaded filename
            checksum: SHA256 checksum of the file

        Returns:
            Relative file path from project root
        """
        now = datetime.utcnow()
        year = now.strftime("%Y")
        month = now.strftime("%m")

        # Sanitize filename
        safe_filename = AudioFileService.sanitize_filename(original_filename)

        # Use first 16 chars of checksum as prefix
        checksum_prefix = checksum[:16]

        # Construct filename: checksum_prefix_original_name.ext
        filename = f"{checksum_prefix}_{safe_filename}"

        # Construct path: uploads/user_{id}/YYYY/MM/filename
        return os.path.join(
            settings.upload_dir,
            f"user_{user_id}",
            year,
            month,
            filename
        )

    @staticmethod
    async def ensure_directory_exists(file_path: str) -> None:
        """
        Ensure the directory for the file path exists.

        Args:
            file_path: Full or relative file path
        """
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @staticmethod
    async def get_file_size(file_path: str) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes
        """
        return os.path.getsize(file_path)

    @staticmethod
    async def extract_metadata(file_path: str) -> Dict[str, Any]:
        """
        Extract audio metadata (duration, sample rate, etc.) using ffprobe.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary with metadata (duration, mime_type, etc.)
        """
        metadata = {
            "duration": None,
            "mime_type": None,
        }

        try:
            import subprocess
            import json

            # Use ffprobe to get audio metadata
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)

                # Get duration from format
                if 'format' in data and 'duration' in data['format']:
                    metadata['duration'] = float(data['format']['duration'])

                # Get mime type from format
                if 'format' in data and 'format_name' in data['format']:
                    format_name = data['format']['format_name']
                    # Map common formats to MIME types
                    mime_map = {
                        'mp3': 'audio/mpeg',
                        'wav': 'audio/wav',
                        'ogg': 'audio/ogg',
                        'm4a': 'audio/mp4',
                        'flac': 'audio/flac',
                        'aac': 'audio/aac',
                    }
                    for fmt, mime in mime_map.items():
                        if fmt in format_name.lower():
                            metadata['mime_type'] = mime
                            break

        except Exception as e:
            # If ffprobe fails, return None for metadata
            # This is acceptable - metadata is optional
            pass

        return metadata

    @staticmethod
    async def check_duplicate(
        db: AsyncSession,
        user_id: str,
        checksum: str
    ) -> Optional[AudioFile]:
        """
        Check if a file with the same checksum already exists for this user.

        Args:
            db: Database session
            user_id: User's ID
            checksum: SHA256 checksum to check

        Returns:
            AudioFile if duplicate exists, None otherwise
        """
        result = await db.execute(
            select(AudioFile).where(
                AudioFile.user_id == user_id,
                AudioFile.checksum == checksum
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_from_upload(
        db: AsyncSession,
        user_id: str,
        uploaded_file: UploadFile
    ) -> tuple[AudioFile, bool]:
        """
        Handle local file upload with deduplication.

        Process:
        1. Save to temp location
        2. Calculate checksum
        3. Check for duplicate
        4. If duplicate, delete temp file and return existing record
        5. If new, move to user folder and create AudioFile record

        Args:
            db: Database session
            user_id: User's ID
            uploaded_file: FastAPI UploadFile

        Returns:
            Tuple of (AudioFile, is_duplicate)
        """
        # Create temp directory if doesn't exist
        temp_dir = os.path.join(settings.upload_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Save to temp location first
        temp_path = os.path.join(temp_dir, f"temp_{user_id}_{uploaded_file.filename}")

        # Write uploaded file to temp location
        async with aiofiles.open(temp_path, 'wb') as f:
            content = await uploaded_file.read()
            await f.write(content)

        try:
            # Calculate checksum
            checksum = await AudioFileService.calculate_checksum(temp_path)

            # Check for duplicate
            existing_file = await AudioFileService.check_duplicate(db, user_id, checksum)

            if existing_file:
                # Duplicate found - delete temp file and return existing record
                os.remove(temp_path)
                return existing_file, True

            # Not a duplicate - generate final path
            final_path = AudioFileService.generate_file_path(
                user_id, uploaded_file.filename, checksum
            )

            # Ensure directory exists
            await AudioFileService.ensure_directory_exists(final_path)

            # Move file to final location
            shutil.move(temp_path, final_path)

            # Get file size
            file_size = await AudioFileService.get_file_size(final_path)

            # Extract metadata
            metadata = await AudioFileService.extract_metadata(final_path)

            # Create AudioFile record
            audio_file = AudioFile(
                user_id=user_id,
                file_path=final_path,
                original_filename=uploaded_file.filename,
                file_size=file_size,
                mime_type=metadata.get('mime_type') or uploaded_file.content_type,
                duration=metadata.get('duration'),
                checksum=checksum,
                source_type="upload"
            )

            db.add(audio_file)
            await db.commit()
            await db.refresh(audio_file)

            return audio_file, False

        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    @staticmethod
    async def create_from_download(
        db: AsyncSession,
        user_id: str,
        downloaded_file_path: str,
        original_filename: str,
        source_url: str,
        source_platform: Optional[str] = None
    ) -> tuple[AudioFile, bool]:
        """
        Create AudioFile from downloaded file (via yt-dlp).

        Args:
            db: Database session
            user_id: User's ID
            downloaded_file_path: Path to the downloaded file (in temp location)
            original_filename: Original filename from source
            source_url: URL the file was downloaded from
            source_platform: Platform name (youtube, soundcloud, etc.)

        Returns:
            Tuple of (AudioFile, is_duplicate)
        """
        # Calculate checksum
        checksum = await AudioFileService.calculate_checksum(downloaded_file_path)

        # Check for duplicate
        existing_file = await AudioFileService.check_duplicate(db, user_id, checksum)

        if existing_file:
            # Duplicate found - delete downloaded file and return existing record
            os.remove(downloaded_file_path)
            return existing_file, True

        # Not a duplicate - generate final path
        final_path = AudioFileService.generate_file_path(
            user_id, original_filename, checksum
        )

        # Ensure directory exists
        await AudioFileService.ensure_directory_exists(final_path)

        # Move file to final location
        shutil.move(downloaded_file_path, final_path)

        # Get file size
        file_size = await AudioFileService.get_file_size(final_path)

        # Extract metadata
        metadata = await AudioFileService.extract_metadata(final_path)

        # Create AudioFile record
        audio_file = AudioFile(
            user_id=user_id,
            file_path=final_path,
            original_filename=original_filename,
            file_size=file_size,
            mime_type=metadata.get('mime_type'),
            duration=metadata.get('duration'),
            checksum=checksum,
            source_type="download",
            source_url=source_url,
            source_platform=source_platform
        )

        db.add(audio_file)
        await db.commit()
        await db.refresh(audio_file)

        return audio_file, False

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        audio_file_id: int
    ) -> Optional[AudioFile]:
        """
        Get audio file by ID.

        Args:
            db: Database session
            audio_file_id: Audio file ID

        Returns:
            AudioFile or None
        """
        result = await db.execute(
            select(AudioFile).where(AudioFile.id == audio_file_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_files(
        db: AsyncSession,
        user_id: str,
        source_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[AudioFile]:
        """
        List user's audio files with pagination and filtering.

        Args:
            db: Database session
            user_id: User's ID
            source_type: Filter by source type ('upload' or 'download')
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of AudioFile records
        """
        query = select(AudioFile).where(AudioFile.user_id == user_id)

        if source_type:
            query = query.where(AudioFile.source_type == source_type)

        query = query.order_by(AudioFile.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def delete_file(
        db: AsyncSession,
        audio_file_id: int,
        user_id: str
    ) -> bool:
        """
        Delete audio file (permission check + file removal).
        Cascade deletes transcriptions via FK constraint.

        Args:
            db: Database session
            audio_file_id: Audio file ID
            user_id: User's ID (for permission check)

        Returns:
            True if deleted, False if not found or permission denied
        """
        audio_file = await AudioFileService.get_by_id(db, audio_file_id)

        if not audio_file:
            return False

        # Permission check
        if audio_file.user_id != user_id:
            return False

        # Delete physical file if it exists
        if os.path.exists(audio_file.file_path):
            try:
                os.remove(audio_file.file_path)
            except Exception:
                # Continue even if file deletion fails
                pass

        # Delete database record (cascades to transcriptions)
        await db.delete(audio_file)
        await db.commit()

        return True

    @staticmethod
    async def count_user_files(
        db: AsyncSession,
        user_id: str,
        source_type: Optional[str] = None
    ) -> int:
        """
        Count user's audio files.

        Args:
            db: Database session
            user_id: User's ID
            source_type: Filter by source type ('upload' or 'download')

        Returns:
            Count of audio files
        """
        from sqlalchemy import func

        query = select(func.count(AudioFile.id)).where(AudioFile.user_id == user_id)

        if source_type:
            query = query.where(AudioFile.source_type == source_type)

        result = await db.execute(query)
        return result.scalar_one()
