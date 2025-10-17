"""
Embed activity - Generate and store embeddings for chunks.

This activity generates semantic embeddings for all chunks and stores them
in the database for fast similarity search.
"""

import logging
from temporalio import activity
from sqlalchemy import select

from app.data import JobChunk, get_db_session
from app.services.embedding_service import generate_embeddings_batch
from app.services.websocket_manager import send_job_update
from ..utils.heartbeat import ProgressTracker
from .models import EmbeddingInput, EmbeddingResult

logger = logging.getLogger(__name__)


@activity.defn
async def embed_chunks_activity(embedding_input: EmbeddingInput) -> EmbeddingResult:
    """
    Generate embeddings for chunks and store in database.

    This activity:
    1. Loads chunks from database (saved by chunk activity)
    2. Generates embeddings for all chunks in batch (efficient)
    3. Updates chunks with embeddings in job_chunks table
    4. Updates job status to completed
    5. Sends final WebSocket notification

    Args:
        embedding_input: Contains job_id (chunks loaded from DB)

    Returns:
        EmbeddingResult with success status and counts
    """
    job_id = embedding_input.job_id

    logger.info("Starting embedding activity", extra={
        "job_id": job_id
    })

    # Create progress tracker
    progress = ProgressTracker(total=100, job_id=job_id)
    progress.update(10, "Loading chunks from database")

    try:
        # Load chunks from database (saved by chunk activity)
        session = await get_db_session()
        async with session:
            # Query chunks for this job, ordered by chunk_index
            select_stmt = select(JobChunk).where(
                JobChunk.job_id == job_id
            ).order_by(JobChunk.chunk_index)
            result = await session.execute(select_stmt)
            chunks = result.scalars().all()

            if not chunks:
                raise ValueError(f"No chunks found in database for job {job_id}")

            logger.info(f"Loaded {len(chunks)} chunks from database", extra={
                "job_id": job_id,
                "chunk_count": len(chunks)
            })

            # Extract text from all chunks for batch processing
            chunk_texts = [chunk.text for chunk in chunks]

            # Generate embeddings in batch (much faster than one-by-one)
            progress.update(10, f"Generating embeddings for {len(chunks)} chunks")
            embeddings = generate_embeddings_batch(chunk_texts)

            progress.update(30, "Embeddings generated, updating database")

            # Update chunks with embeddings
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            progress.update(20, "Saving embeddings to database")
            await session.commit()

            # Update job status to completed
            from app.data import Job
            job = await session.get(Job, job_id)
            if job:
                job.status = "completed"
                await session.commit()

            progress.update(20, "Job completed successfully")

        logger.info("Embedding activity completed successfully", extra={
            "job_id": job_id,
            "chunk_count": len(chunks),
            "embedding_count": len(embeddings)
        })

        # Send final WebSocket notification
        await send_job_update(
            job_id,
            "completed",
            progress=100
        )

        return EmbeddingResult(
            job_id=job_id,
            success=True,
            chunk_count=len(chunks),
            embedding_count=len(embeddings)
        )

    except Exception as e:
        logger.error("Embedding activity failed", extra={
            "job_id": job_id,
            "error": str(e)
        }, exc_info=True)

        # Update job status to failed
        session = await get_db_session()
        async with session:
            from app.data import Job
            job = await session.get(Job, job_id)
            if job:
                job.status = "failed"
                await session.commit()

        # Send error notification
        await send_job_update(job_id, "failed", error=str(e))

        # Send heartbeat with error
        activity.heartbeat(f"Embedding failed: {str(e)}")

        raise
