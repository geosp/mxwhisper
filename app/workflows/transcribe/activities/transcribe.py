"""
Transcribe activity - Whisper audio transcription.

This activity handles audio transcription using Whisper and stores the results.
It does NOT generate embeddings - that's handled by the embed activity.
"""

import json
import logging
from temporalio import activity

from app.data import Job, get_db_session
from app.services.websocket_manager import send_job_update
from ..services.whisper_service import transcribe_audio
from .models import TranscriptionSummary

logger = logging.getLogger(__name__)


@activity.defn
async def transcribe_activity(job_id: int) -> TranscriptionSummary:
    """
    Transcribe audio file using Whisper.

    This activity:
    1. Loads the job from database
    2. Transcribes the audio using Whisper
    3. Stores transcript and segments
    4. Returns a lightweight summary

    Args:
        job_id: ID of the job to transcribe

    Returns:
        TranscriptionSummary with basic metadata
    """
    logger.info("Starting transcription activity", extra={"job_id": job_id})

    # Send initial heartbeat
    activity.heartbeat("Initializing transcription")

    session = await get_db_session()
    async with session:
        # Load job
        job = await session.get(Job, job_id)
        if not job:
            logger.error("Job not found for transcription", extra={"job_id": job_id})
            raise ValueError(f"Job {job_id} not found")

        logger.info("Job found, updating status to processing", extra={
            "job_id": job.id,
            "audio_filename": job.filename,
            "current_status": job.status
        })

        # Update status
        job.status = "processing"
        await session.commit()
        await send_job_update(job.id, job.status)

        try:
            # Transcribe the audio file
            result = await transcribe_audio(job.file_path, job_id=job.id)

            # Store transcript and segments
            job.transcript = result["text"]
            segments = result.get("segments", [])
            job.segments = json.dumps(segments)

            # Note: We do NOT generate embeddings here anymore
            # That's handled by the embed_chunks_activity

            logger.info("Transcription completed successfully", extra={
                "job_id": job.id,
                "transcript_length": len(result["text"]),
                "segment_count": len(segments),
                "language": result.get("language")
            })

            # Create lightweight summary for Temporal return value
            summary = TranscriptionSummary(
                job_id=job.id,
                success=True,
                segment_count=len(segments),
                character_count=len(result["text"]),
                language=result.get("language"),
                duration=segments[-1]["end"] if segments else None
            )

            # Commit changes
            await session.commit()

            # Send WebSocket update (status still "processing" - chunking/embedding next)
            await send_job_update(
                job.id,
                "processing",
                progress=60  # Transcription is ~60% of total work
            )

            return summary

        except Exception as e:
            logger.error("Transcription failed", extra={
                "job_id": job_id,
                "error": str(e),
                "audio_path": job.file_path
            }, exc_info=True)

            # Update job status to failed
            job.status = "failed"
            await session.commit()

            # Send error update via WebSocket
            await send_job_update(job_id, "failed", error=str(e))

            # Send final heartbeat with error
            activity.heartbeat(f"Transcription failed: {str(e)}")

            raise
