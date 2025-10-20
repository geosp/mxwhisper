"""
Download activity for DownloadAudioWorkflow
"""
import logging
import os
import queue
import asyncio
from typing import Dict, Any

from temporalio import activity
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.services.download_service import DownloadService
from app.services.audio_file_service import AudioFileService
from app.data.models import Job

logger = logging.getLogger(__name__)


@activity.defn
async def download_audio_activity(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download audio from URL using yt-dlp and create AudioFile record.

    Args:
        input_data: Dictionary with:
            - job_id: int - Job ID for tracking
            - user_id: str - User's ID
            - source_url: str - URL to download from

    Returns:
        Dictionary with:
            - audio_file_id: int
            - checksum: str
            - file_path: str
            - is_duplicate: bool
            - platform: str
            - duration: float

    Raises:
        ValueError: If download fails or URL is invalid
    """
    job_id = input_data["job_id"]
    user_id = input_data["user_id"]
    source_url = input_data["source_url"]

    activity.logger.info(f"Starting audio download", extra={
        "job_id": job_id,
        "user_id": user_id,
        "source_url": source_url
    })

    # Send initial heartbeat
    activity.heartbeat("Initializing download")

    # Create temp directory for downloads
    temp_dir = os.path.join(settings.upload_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Update job status to processing
    engine = create_async_engine(settings.database_url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        # Update job status
        result = await session.get(Job, job_id)
        if result:
            result.status = "processing"
            await session.commit()

    try:
        # Download audio using yt-dlp with progress monitoring
        activity.logger.info(f"Downloading from URL: {source_url}")

        # Create queue for progress updates
        progress_queue = queue.Queue()

        # Task to process heartbeats from the queue
        async def process_heartbeats():
            while True:
                try:
                    d = progress_queue.get_nowait()
                    status = d.get('status')

                    if status == 'downloading':
                        # Extract progress information
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                        speed = d.get('speed', 0)
                        eta = d.get('eta', 0)

                        if total > 0:
                            percent = (downloaded / total) * 100
                            # Send heartbeat with progress info
                            activity.heartbeat(f"Downloading: {percent:.1f}% complete")
                        else:
                            # No total size available, just report bytes downloaded
                            mb_downloaded = downloaded / (1024 * 1024)
                            activity.heartbeat(f"Downloading: {mb_downloaded:.1f} MB downloaded")

                    elif status == 'finished':
                        activity.heartbeat("Download finished, processing file")

                    elif status == 'error':
                        activity.logger.error(f"Download error: {d.get('error')}")

                except queue.Empty:
                    await asyncio.sleep(0.1)

        # Start the heartbeat processing task
        heartbeat_task = asyncio.create_task(process_heartbeats())

        download_result = await DownloadService.download_audio(
            source_url=source_url,
            output_dir=temp_dir,
            user_id=user_id,
            progress_queue=progress_queue
        )

        # Cancel the heartbeat task after download completes
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        activity.logger.info(f"Download completed", extra={
            "job_id": job_id,
            "platform": download_result["platform"],
            "file_path": download_result["file_path"]
        })

        # Create AudioFile record (includes checksum, deduplication, move to final location)
        activity.heartbeat("Creating audio file record")
        async with async_session_maker() as session:
            audio_file, is_duplicate = await AudioFileService.create_from_download(
                db=session,
                user_id=user_id,
                downloaded_file_path=download_result["file_path"],
                original_filename=download_result["original_filename"],
                source_url=source_url,
                source_platform=download_result["platform"]
            )

            # Update job with audio_file_id
            job = await session.get(Job, job_id)
            if job:
                job.audio_file_id = audio_file.id
                job.status = "completed"
                await session.commit()

            activity.logger.info(f"AudioFile created", extra={
                "job_id": job_id,
                "audio_file_id": audio_file.id,
                "is_duplicate": is_duplicate,
                "checksum": audio_file.checksum
            })

            return {
                "audio_file_id": audio_file.id,
                "checksum": audio_file.checksum,
                "file_path": audio_file.file_path,
                "is_duplicate": is_duplicate,
                "platform": download_result["platform"],
                "duration": audio_file.duration
            }

    except Exception as e:
        activity.logger.error(f"Download failed", extra={
            "job_id": job_id,
            "source_url": source_url,
            "error": str(e)
        }, exc_info=True)

        # Update job status to failed
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if job:
                job.status = "failed"
                await session.commit()

        raise

    finally:
        await engine.dispose()
