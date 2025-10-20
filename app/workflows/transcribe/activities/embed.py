"""
Embed activity - Updated for media sourcing architecture.
Works with TranscriptionChunk models.
"""

import logging
from typing import Dict, Any

from temporalio import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.data.models import Job, Transcription, TranscriptionChunk
from app.services.embedding_service import generate_embedding, generate_embeddings_batch
from app.services.websocket_manager import send_job_update

logger = logging.getLogger(__name__)


@activity.defn
async def embed_chunks_activity(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate and store embeddings for transcription chunks .

    This activity:
    1. Loads TranscriptionChunk records from database
    2. Generates embeddings for each chunk's text
    3. Stores embeddings in the chunks
    4. Returns summary

    Args:
        input_data: Dictionary with:
            - transcription_id: int - Transcription ID
            - job_id: int - Job ID for tracking

    Returns:
        Dictionary with embedding results
    """
    transcription_id = input_data["transcription_id"]
    job_id = input_data["job_id"]

    activity.logger.info(f"Starting embedding activity ", extra={
        "transcription_id": transcription_id,
        "job_id": job_id
    })

    activity.heartbeat("Loading chunks for embedding")

    engine = create_async_engine(settings.database_url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:
            # Load all chunks for this transcription
            result = await session.execute(
                select(TranscriptionChunk)
                .where(TranscriptionChunk.transcription_id == transcription_id)
                .order_by(TranscriptionChunk.chunk_index)
            )
            chunks = result.scalars().all()

            if not chunks:
                activity.logger.warning(f"No chunks found for transcription", extra={
                    "transcription_id": transcription_id
                })
                return {
                    "transcription_id": transcription_id,
                    "success": True,
                    "embedding_count": 0
                }

            activity.logger.info(f"Loaded chunks", extra={
                "transcription_id": transcription_id,
                "chunk_count": len(chunks)
            })

            # Extract texts for embedding
            chunk_texts = [chunk.text for chunk in chunks]

            # Send heartbeat before potentially long operation
            activity.heartbeat(f"Generating embeddings for {len(chunks)} chunks")

            # Generate embeddings
            activity.logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embeddings = generate_embeddings_batch(chunk_texts)

            # Store embeddings in chunks
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk.embedding = embedding

                # Send periodic heartbeat for large batches
                if i > 0 and i % 10 == 0:
                    activity.heartbeat(f"Stored {i}/{len(chunks)} embeddings")

            await session.commit()

            activity.logger.info(f"Embeddings stored successfully", extra={
                "transcription_id": transcription_id,
                "embedding_count": len(embeddings)
            })

            # Update job status to completed
            job = await session.get(Job, job_id)
            if job:
                job.status = "completed"
                await session.commit()
                await send_job_update(job.id, "completed", progress=100)

            return {
                "transcription_id": transcription_id,
                "success": True,
                "embedding_count": len(embeddings)
            }

    except Exception as e:
        activity.logger.error(f"Embedding failed", extra={
            "transcription_id": transcription_id,
            "job_id": job_id,
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
