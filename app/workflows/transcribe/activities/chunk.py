"""
Chunk activity - Topic-based semantic chunking using Ollama.

This activity analyzes transcripts to identify topic boundaries and creates
semantically coherent chunks for better search relevance.
"""

import logging
from typing import List, Dict, Any, Optional
from temporalio import activity
import httpx

from app.config import settings
from ..services.ollama_service import OllamaChunker
from ..utils.heartbeat import ProgressTracker, HeartbeatPacemaker
from .models import ChunkingInput, ChunkingResult, ChunkMetadata

logger = logging.getLogger(__name__)


@activity.defn
async def chunk_with_ollama_activity(chunking_input: ChunkingInput) -> ChunkingResult:
    """
    Analyze transcript and create topic-based semantic chunks using Ollama.

    This activity:
    1. Uses Ollama LLM to identify topic boundaries in the transcript
    2. Creates chunks aligned with semantic/topic shifts
    3. Maps chunks to Whisper segments for timestamp information
    4. Falls back to sentence-based chunking if Ollama fails

    Args:
        chunking_input: Contains job_id, transcript, and segments

    Returns:
        ChunkingResult with chunks and metadata
    """
    job_id = chunking_input.job_id

    # Fetch transcript and segments from DB if not provided
    # This avoids passing large payloads through Temporal
    if chunking_input.transcript is None or chunking_input.segments is None:
        from app.data import Job, get_db_session
        import json

        session = await get_db_session()
        async with session:
            job = await session.get(Job, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            transcript = job.transcript or ""
            segments = json.loads(job.segments) if job.segments else []
    else:
        transcript = chunking_input.transcript
        segments = chunking_input.segments

    logger.info("Starting chunking activity", extra={
        "job_id": job_id,
        "transcript_length": len(transcript),
        "segment_count": len(segments)
    })

    # Check if chunking is enabled
    if not settings.enable_semantic_chunking:
        logger.info("Semantic chunking disabled, creating single chunk", extra={
            "job_id": job_id
        })
        return await _create_single_chunk(job_id, transcript, segments)

    # Create progress tracker for heartbeats
    progress = ProgressTracker(total=100, job_id=job_id)
    progress.update(5, "Initializing chunking")

    try:
        # Initialize Ollama chunker
        chunker = OllamaChunker()

        # Quick health check - try to connect to Ollama
        health_check_passed = await _check_ollama_health(chunker)
        if not health_check_passed:
            logger.warning("Ollama health check failed, falling back to sentence chunking", extra={
                "job_id": job_id
            })
            return await _create_sentence_chunks(job_id, transcript, segments, progress)

        async with HeartbeatPacemaker("Analyzing topics with Ollama", interval=10):
            # Perform topic-based chunking
            chunks = await chunker.chunk_by_topics(
                transcript=transcript,
                segments=segments,
                progress=progress
            )

        progress.update(50, f"Successfully created {len(chunks)} semantic chunks")

        # Save chunks to database (without embeddings - those come later)
        await _save_chunks_to_db(job_id, chunks, progress)

        logger.info("Chunking completed successfully", extra={
            "job_id": job_id,
            "chunk_count": len(chunks),
            "chunking_method": "ollama"
        })

        return ChunkingResult(
            job_id=job_id,
            success=True,
            chunk_count=len(chunks),
            chunks=chunks,
            chunking_method="ollama"
        )

    except Exception as e:
        logger.error("Chunking activity failed", extra={
            "job_id": job_id,
            "error": str(e)
        }, exc_info=True)

        # Note: OllamaChunker already has fallback logic internally,
        # so this error means even the fallback failed
        activity.heartbeat(f"Chunking failed: {str(e)}")
        raise


async def _create_single_chunk(job_id: int, transcript: str, segments: List[Dict[str, Any]]) -> ChunkingResult:
    """
    Create a single chunk from the entire transcript (no chunking).

    Used when semantic chunking is disabled or for very short transcripts.
    """
    # Get timestamps from first and last segments
    start_time = None
    end_time = None
    if segments:
        start_time = segments[0].get("start", 0.0)
        end_time = segments[-1].get("end", 0.0)

    chunk = ChunkMetadata(
        chunk_index=0,
        text=transcript,
        topic_summary=None,  # No topic analysis
        keywords=None,
        confidence=None,
        start_char_pos=0,
        end_char_pos=len(transcript),
        start_time=start_time,
        end_time=end_time,
    )

    # Save chunk to database
    await _save_chunks_to_db(job_id, [chunk])

    return ChunkingResult(
        job_id=job_id,
        success=True,
        chunk_count=1,
        chunks=[chunk],
        chunking_method="single"
    )


async def _check_ollama_health(chunker: OllamaChunker) -> bool:
    """
    Quick health check for Ollama service.
    
    Returns True if Ollama is responsive, False otherwise.
    """
    try:
        # Try a simple request to check if Ollama is available
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{chunker.base_url}/api/tags")
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
        return False


async def _create_sentence_chunks(job_id: int, transcript: str, segments: List[Dict[str, Any]], progress: ProgressTracker) -> ChunkingResult:
    """
    Create sentence-based chunks from the transcript.

    Used as a fallback when semantic chunking is disabled or fails.
    """
    logger.info("Creating sentence-based chunks", extra={
        "job_id": job_id
    })

    # Split transcript into sentences using Whisper segments
    sentences = []
    for segment in segments:
        start = segment.get("start", 0.0)
        end = segment.get("end", 0.0)
        text = segment.get("text", "").strip()

        if text:
            sentences.append(ChunkMetadata(
                chunk_index=len(sentences),
                text=text,
                topic_summary=None,  # No topic analysis
                keywords=None,
                confidence=None,
                start_char_pos=0,
                end_char_pos=len(text),
                start_time=start,
                end_time=end,
            ))

    progress.update(50, f"Successfully created {len(sentences)} sentence chunks")

    # Save chunks to database
    await _save_chunks_to_db(job_id, sentences, progress)

    return ChunkingResult(
        job_id=job_id,
        success=True,
        chunk_count=len(sentences),
        chunks=sentences,
        chunking_method="sentence"
    )


async def _save_chunks_to_db(
    job_id: int,
    chunks: List[ChunkMetadata],
    progress: Optional[ProgressTracker] = None
) -> None:
    """
    Save chunks to the database without embeddings.

    Embeddings will be added later by the embed activity.
    This avoids passing large chunk data through Temporal event history.
    """
    from app.data import JobChunk, get_db_session

    if progress:
        progress.update(5, f"Saving {len(chunks)} chunks to database")

    session = await get_db_session()
    async with session:
        # Delete existing chunks for this job (in case of retry)
        await session.execute(
            JobChunk.__table__.delete().where(JobChunk.job_id == job_id)
        )

        # Create new chunk records without embeddings
        for chunk in chunks:
            job_chunk = JobChunk(
                job_id=job_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                topic_summary=chunk.topic_summary,
                keywords=chunk.keywords,
                confidence=chunk.confidence,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                start_char_pos=chunk.start_char_pos,
                end_char_pos=chunk.end_char_pos,
                embedding=None  # Will be set by embed activity
            )
            session.add(job_chunk)

        await session.commit()

        logger.info(f"Saved {len(chunks)} chunks to database for job {job_id}")

        if progress:
            progress.update(5, f"Saved {len(chunks)} chunks to database")
