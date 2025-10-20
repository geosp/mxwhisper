"""
Transcribe activity - Updated for media sourcing architecture.
Works with AudioFile and Transcription models instead of Job.
"""

import json
import logging
from typing import Dict, Any

from temporalio import activity
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.data.models import Job, AudioFile, Transcription
from app.services.transcription_service import TranscriptionService
from app.services.websocket_manager import send_job_update
from ..services.whisper_service import transcribe_audio

logger = logging.getLogger(__name__)


@activity.defn
async def transcribe_activity(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transcribe audio file using Whisper.

    This activity:
    1. Loads the transcription and audio file from database
    2. Transcribes the audio using Whisper
    3. Updates Transcription record with results
    4. Returns a lightweight summary

    Args:
        input_data: Dictionary with:
            - transcription_id: int - Transcription ID
            - job_id: int - Job ID for tracking

    Returns:
        Dictionary with transcription results
    """
    transcription_id = input_data["transcription_id"]
    job_id = input_data["job_id"]

    activity.logger.info(f"Starting transcription activity", extra={
        "transcription_id": transcription_id,
        "job_id": job_id
    })

    # Send initial heartbeat
    activity.heartbeat("Initializing transcription")

    engine = create_async_engine(settings.database_url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:
            # Load transcription and audio file
            transcription = await session.get(Transcription, transcription_id)
            if not transcription:
                raise ValueError(f"Transcription {transcription_id} not found")

            audio_file = await session.get(AudioFile, transcription.audio_file_id)
            if not audio_file:
                raise ValueError(f"AudioFile {transcription.audio_file_id} not found")

            # Update job status
            job = await session.get(Job, job_id)
            if job:
                job.status = "processing"
                await session.commit()
                await send_job_update(job.id, job.status)

            # Update transcription status
            transcription.status = "processing"
            await session.commit()

            activity.logger.info(f"Transcribing audio file", extra={
                "transcription_id": transcription.id,
                "audio_file_id": audio_file.id,
                "file_path": audio_file.file_path,
                "original_filename": audio_file.original_filename
            })

            # Transcribe the audio file
            result = await transcribe_audio(
                audio_file.file_path,
                job_id=job_id  # For heartbeat tracking
            )

            # Update transcription with results
            transcript_text = result["text"]
            segments = result.get("segments", [])
            language = result.get("language", "unknown")

            # Calculate average confidence
            confidences = [seg.get("confidence", 0.0) for seg in segments if "confidence" in seg]
            avg_confidence = sum(confidences) / len(confidences) if confidences else None

            # Get processing time from result
            processing_time = result.get("processing_time")

            # Update transcription using service
            await TranscriptionService.update_transcription_result(
                db=session,
                transcription_id=transcription.id,
                transcript=transcript_text,
                language=language,
                avg_confidence=avg_confidence if avg_confidence else 0.0,
                segments=segments,
                processing_time=processing_time
            )

            activity.logger.info(f"Transcription completed successfully", extra={
                "transcription_id": transcription.id,
                "job_id": job_id,
                "transcript_length": len(transcript_text),
                "segment_count": len(segments),
                "language": language
            })

            # Send WebSocket update
            if job:
                await send_job_update(
                    job.id,
                    "processing",
                    progress=60  # Transcription is ~60% of total work
                )

            return {
                "transcription_id": transcription.id,
                "success": True,
                "segment_count": len(segments),
                "character_count": len(transcript_text),
                "language": language,
                "segments": segments  # For chunking activity
            }

    except Exception as e:
        activity.logger.error(f"Transcription failed", extra={
            "transcription_id": transcription_id,
            "job_id": job_id,
            "error": str(e)
        }, exc_info=True)

        # Mark transcription as failed
        async with async_session_maker() as session:
            await TranscriptionService.mark_as_failed(
                db=session,
                transcription_id=transcription_id,
                error_message=str(e)
            )

            # Update job status
            job = await session.get(Job, job_id)
            if job:
                job.status = "failed"
                await session.commit()

        raise

    finally:
        await engine.dispose()
