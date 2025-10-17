import whisper
import logging
import tqdm
from dataclasses import dataclass
from temporalio import activity

from app.config import settings
from app.data import Job, get_db_session
from app.services.websocket_manager import send_job_update

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionSummary:
    """Lightweight summary of transcription results to avoid Temporal event history bloat."""
    job_id: int
    success: bool
    segment_count: int
    character_count: int
    language: str | None
    duration: float | None

# Model will be loaded lazily
model = None

class ProgressCallback:
    """Callback class to capture Whisper transcription progress."""
    
    def __init__(self, job_id: int):
        self.job_id = job_id
        self.last_progress = 0
    
    async def update_progress(self, current: int, total: int):
        """Update progress and send WebSocket notification."""
        if total > 0:
            progress = int((current / total) * 100)
            # Only send updates when progress changes significantly (every 5%)
            if progress >= self.last_progress + 5 or progress == 100:
                self.last_progress = progress
                await send_job_update(self.job_id, "processing", progress=progress)
                # Send heartbeat to Temporal to prevent timeouts
                activity.heartbeat(f"Progress: {progress}%")
                logger.debug("Progress update sent", extra={
                    "job_id": self.job_id,
                    "progress": progress,
                    "current": current,
                    "total": total
                })

class WhisperProgressBar(tqdm.tqdm):
    """Custom progress bar that sends WebSocket updates."""
    
    def __init__(self, *args, callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.callback = callback
        self._current = 0
    
    def update(self, n=1):
        super().update(n)
        self._current += n
        if self.callback:
            # Run the async callback in a thread-safe way
            import asyncio
            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, use asyncio.create_task
                    loop.create_task(self.callback.update_progress(self._current, self.total))
                else:
                    # If no loop is running, we can't send async updates
                    # This shouldn't happen in our Temporal activity context
                    pass
            except RuntimeError:
                # No event loop, skip async update
                pass

def get_whisper_model():
    """Lazy load the Whisper model."""
    global model
    if model is None:
        model_size = settings.whisper_model_size
        logger.info("Loading Whisper model", extra={"model": model_size})
        model = whisper.load_model(model_size)
        logger.info("Whisper model loaded successfully")
    return model

@activity.defn
async def transcribe_activity(job_id: int) -> TranscriptionSummary:
    logger.info("Starting transcription activity", extra={"job_id": job_id})
    
    session = await get_db_session()
    async with session:
        job = await session.get(Job, job_id)
        if not job:
            logger.error("Job not found for transcription", extra={"job_id": job_id})
            raise ValueError("Job not found")

        logger.info("Job found, updating status to processing", extra={
            "job_id": job.id,
            "file_filename": job.filename,
            "current_status": job.status
        })
        job.status = "processing"
        await session.commit()
        await send_job_update(job.id, job.status)

        try:
            logger.info("Starting Whisper transcription", extra={
                "job_id": job.id,
                "file_path": job.file_path
            })
            
            # Create progress callback
            progress_callback = ProgressCallback(job.id)
            
            # Send initial progress update
            await send_job_update(job.id, "processing", progress=0)
            
            # Transcribe the file with progress tracking
            whisper_model = get_whisper_model()
            
            # Send initial heartbeat
            activity.heartbeat("Starting transcription")
            
            # Temporarily override tqdm.tqdm to capture progress
            original_tqdm = tqdm.tqdm
            tqdm.tqdm = lambda *args, **kwargs: WhisperProgressBar(*args, callback=progress_callback, **kwargs)
            
            try:
                # Start transcription (this will now send progress updates)
                result = whisper_model.transcribe(job.file_path, verbose=False)
            finally:
                # Restore original tqdm
                tqdm.tqdm = original_tqdm
            
            # Send final heartbeat
            activity.heartbeat("Transcription completed")
            
            job.transcript = result["text"]
            # Store segments data as JSON for SRT generation
            import json
            segments = result.get("segments", [])
            job.segments = json.dumps(segments)
            job.status = "completed"

            # Create lightweight summary for Temporal return value
            summary = TranscriptionSummary(
                job_id=job.id,
                success=True,
                segment_count=len(segments),
                character_count=len(result["text"]),
                language=result.get("language"),
                duration=segments[-1]["end"] if segments else None
            )

            logger.info("Transcription completed successfully", extra={
                "job_id": job.id,
                "transcript_length": len(result["text"]),
                "segment_count": summary.segment_count,
                "status": job.status
            })

            # Send completion update with transcript
            await send_job_update(job.id, "completed", transcript=result["text"], progress=100)

            return summary
            
        except Exception as e:
            logger.error("Transcription failed", extra={
                "job_id": job_id,
                "error": str(e),
                "audio_path": job.file_path
            })
            activity.heartbeat(f"Transcription failed: {str(e)}")
            
            # Send error update via WebSocket
            await send_job_update(job_id, "failed", error=str(e))
            
            raise
        finally:
            await session.commit()
            logger.debug("Job status updated and WebSocket notification sent", extra={
                "job_id": job.id,
                "final_status": job.status
            })