"""
Chunk activity - Updated for media sourcing architecture.
Works with Transcription and TranscriptionChunk models.
"""

import logging
from typing import Dict, Any, List

from temporalio import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.data.models import Job, Transcription, TranscriptionChunk
from app.services.transcription_service import TranscriptionService
from app.services.websocket_manager import send_job_update
from ..services.ollama_service import OllamaChunker
from ..utils.heartbeat import ProgressTracker

logger = logging.getLogger(__name__)


@activity.defn
async def chunk_with_ollama_activity(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create semantic chunks using Ollama .

    This activity:
    1. Loads transcription from database
    2. Analyzes transcript with Ollama for topic-based chunking
    3. Creates TranscriptionChunk records
    4. Returns summary

    Args:
        input_data: Dictionary with:
            - transcription_id: int - Transcription ID
            - job_id: int - Job ID for tracking
            - segments: List[Dict] - Whisper segments (passed from transcribe activity)

    Returns:
        Dictionary with chunking results
    """
    transcription_id = input_data["transcription_id"]
    job_id = input_data["job_id"]

    activity.heartbeat("Analyzing transcript for chunking")

    engine = create_async_engine(settings.database_url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:
            # Load transcription
            transcription = await session.get(Transcription, transcription_id)
            if not transcription:
                raise ValueError(f"Transcription {transcription_id} not found")

            transcript = transcription.transcript

            # Load segments from transcription

            segments = transcription.segments if transcription.segments else []

            activity.logger.info(f"Loaded transcript", extra={
                "transcription_id": transcription.id,
                "transcript_length": len(transcript)
            })

            # Analyze with Ollama if enabled
            if settings.enable_semantic_chunking and settings.chunking_strategy == "ollama":
                activity.logger.info("Using Ollama for semantic chunking")

                try:
                    # Create progress tracker for heartbeats
                    progress = ProgressTracker(total=100)

                    # Use OllamaChunker for topic-based chunking
                    chunker = OllamaChunker()
                    chunk_metadata_list = await chunker.chunk_by_topics(
                        transcript=transcript,
                        segments=segments,
                        progress=progress
                    )

                    # Convert ChunkMetadata to dict format for service
                    chunks = [
                        {
                            "text": chunk.text,
                            "start_time": chunk.start_time,
                            "end_time": chunk.end_time,
                            "start_char_pos": chunk.start_char_pos,
                            "end_char_pos": chunk.end_char_pos,
                            "topic_summary": chunk.topic_summary,
                            "keywords": chunk.keywords,
                            "confidence": chunk.confidence
                        }
                        for chunk in chunk_metadata_list
                    ]
                    chunking_method = "ollama"
                except Exception as ollama_error:
                    activity.logger.error(
                        f"Ollama chunking failed with details",
                        extra={
                            "error": str(ollama_error),
                            "error_type": type(ollama_error).__name__,
                            "transcript_length": len(transcript),
                            "segment_count": len(segments)
                        },
                        exc_info=True
                    )
                    activity.logger.warning(
                        f"Ollama chunking failed, falling back to simple chunking",
                        extra={"error": str(ollama_error)}
                    )
                    chunks = _simple_chunk_transcript(transcript, segments)
                    chunking_method = "simple_fallback"
            else:
                activity.logger.info("Using simple chunking strategy")
                chunks = _simple_chunk_transcript(transcript, segments)
                chunking_method = "simple"

            activity.logger.info(f"Chunking analysis completed", extra={
                "transcription_id": transcription.id,
                "chunk_count": len(chunks),
                "chunking_method": chunking_method
            })

            # Create TranscriptionChunk records
            chunks_data = []
            for i, chunk in enumerate(chunks):
                chunk_data = {
                    "chunk_index": i,
                    "text": chunk.get("text", ""),
                    "start_time": chunk.get("start_time"),
                    "end_time": chunk.get("end_time"),
                    "start_char_pos": chunk.get("start_char_pos"),
                    "end_char_pos": chunk.get("end_char_pos"),
                    "topic_summary": chunk.get("topic_summary"),
                    "keywords": chunk.get("keywords"),
                    "confidence": chunk.get("confidence")
                }
                chunks_data.append(chunk_data)

            # Save chunks using service
            await TranscriptionService.create_chunks(
                db=session,
                transcription_id=transcription.id,
                chunks_data=chunks_data
            )

            activity.logger.info(f"Chunks saved to database", extra={
                "transcription_id": transcription.id,
                "chunk_count": len(chunks)
            })

            # Send WebSocket update
            job = await session.get(Job, job_id)
            if job:
                await send_job_update(
                    job.id,
                    "processing",
                    progress=80  # Chunking complete, embedding next
                )

            return {
                "transcription_id": transcription.id,
                "success": True,
                "chunk_count": len(chunks),
                "chunking_method": chunking_method
            }

    except Exception as e:
        activity.logger.error(f"Chunking failed", extra={
            "transcription_id": transcription_id,
            "job_id": job_id,
            "error": str(e)
        }, exc_info=True)
        raise

    finally:
        await engine.dispose()


def _simple_chunk_transcript(transcript: str, segments: List[Dict]) -> List[Dict]:
    """
    Fallback simple chunking based on character count.

    Args:
        transcript: Full transcript text
        segments: Whisper segments

    Returns:
        List of chunk dictionaries
    """
    chunks = []
    chunk_size = 500  # characters
    chunk_overlap = 50  # characters

    start_pos = 0
    chunk_index = 0

    while start_pos < len(transcript):
        end_pos = min(start_pos + chunk_size, len(transcript))

        # Try to break at sentence boundary
        if end_pos < len(transcript):
            # Look for sentence ending
            for delimiter in ['. ', '! ', '? ', '\n']:
                last_delimiter = transcript[start_pos:end_pos].rfind(delimiter)
                if last_delimiter > chunk_size // 2:  # Don't break too early
                    end_pos = start_pos + last_delimiter + len(delimiter)
                    break

        chunk_text = transcript[start_pos:end_pos].strip()

        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "start_char_pos": start_pos,
                "end_char_pos": end_pos,
                "start_time": None,  # Simple chunking doesn't have timing
                "end_time": None
            })
            chunk_index += 1

        # Move to next chunk with overlap
        start_pos = end_pos - chunk_overlap
        if start_pos >= len(transcript) - chunk_overlap:
            break

    return chunks
