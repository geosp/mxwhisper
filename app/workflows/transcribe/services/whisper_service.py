"""
Whisper service for audio transcription.

Handles Whisper model loading, transcription, and progress tracking.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

import tqdm
import whisper

from app.config import settings
from app.services.websocket_manager import send_job_update
from temporalio import activity

logger = logging.getLogger(__name__)

# Global model cache (lazy loaded)
_whisper_model = None


class ProgressCallback:
    """Callback class to capture Whisper transcription progress."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self.last_progress = 0

    async def update_progress(self, current: int, total: int):
        """Update progress and send WebSocket notification with heartbeat."""
        if total > 0:
            progress = int((current / total) * 100)
            # Only send updates when progress changes significantly (every 5%)
            if progress >= self.last_progress + 5 or progress == 100:
                self.last_progress = progress
                await send_job_update(self.job_id, "processing", progress=progress)
                # Send heartbeat to Temporal to prevent timeouts
                activity.heartbeat(f"Transcription progress: {progress}%")
                logger.debug("Transcription progress update sent", extra={
                    "job_id": self.job_id,
                    "progress": progress,
                    "current": current,
                    "total": total
                })


class WhisperProgressBar(tqdm.tqdm):
    """Custom progress bar that sends WebSocket updates and heartbeats."""

    def __init__(self, *args, callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.callback = callback
        self._current = 0

    def update(self, n=1):
        super().update(n)
        self._current += n
        if self.callback:
            # Run the async callback in a thread-safe way
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.callback.update_progress(self._current, self.total))
            except RuntimeError:
                # No event loop, skip async update
                pass


def get_whisper_model():
    """
    Lazy load the Whisper model.

    The model is cached globally to avoid reloading on every transcription.
    """
    global _whisper_model
    if _whisper_model is None:
        model_size = settings.whisper_model_size
        logger.info("Loading Whisper model", extra={"model": model_size})
        _whisper_model = whisper.load_model(model_size)
        logger.info("Whisper model loaded successfully")
    return _whisper_model


async def transcribe_audio(
    audio_path: str,
    job_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Transcribe audio file using Whisper.

    Args:
        audio_path: Path to the audio file
        job_id: Optional job ID for progress tracking

    Returns:
        Whisper transcription result with text, segments, and metadata
    """
    logger.info("Starting Whisper transcription", extra={
        "job_id": job_id,
        "audio_path": audio_path
    })

    # Send initial heartbeat
    activity.heartbeat("Loading Whisper model")

    # Load model
    whisper_model = get_whisper_model()

    # Send heartbeat after model load
    activity.heartbeat("Starting transcription")

    # Set up progress tracking if job_id provided
    if job_id:
        progress_callback = ProgressCallback(job_id)
        await send_job_update(job_id, "processing", progress=0)

        # Temporarily override tqdm to capture progress
        original_tqdm = tqdm.tqdm
        tqdm.tqdm = lambda *args, **kwargs: WhisperProgressBar(
            *args, callback=progress_callback, **kwargs
        )
    else:
        original_tqdm = None

    try:
        # Transcribe the file
        result = whisper_model.transcribe(audio_path, verbose=False)

        # Send final heartbeat
        activity.heartbeat("Transcription completed")

        logger.info("Whisper transcription completed", extra={
            "job_id": job_id,
            "transcript_length": len(result.get("text", "")),
            "segment_count": len(result.get("segments", [])),
            "language": result.get("language")
        })

        return result

    finally:
        # Restore original tqdm if we overrode it
        if original_tqdm is not None:
            tqdm.tqdm = original_tqdm
