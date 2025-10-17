from datetime import timedelta
import logging

from temporalio import workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)

# Don't import activities here to avoid heavy dependencies in workflow validation
# Use string names for activity execution instead


@workflow.defn
class TranscribeWorkflow:
    @workflow.run
    async def run(self, job_id: int) -> dict:
        """
        Run complete transcription workflow with semantic chunking.

        Workflow steps:
        1. Transcribe audio with Whisper
        2. Analyze transcript and create semantic chunks (Ollama)
        3. Generate and store embeddings for chunks

        Args:
            job_id: ID of the job to process

        Returns:
            dict: Minimal summary (chunk_count, success) to avoid event history bloat
        """
        logger.info("Starting transcription workflow", extra={
            "job_id": job_id,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id
        })

        try:
            # Step 1: Transcribe audio with Whisper
            logger.info("Step 1: Transcribing audio", extra={"job_id": job_id})
            transcription_result = await workflow.execute_activity(
                "transcribe_activity",
                job_id,
                start_to_close_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            logger.info("Transcription completed", extra={
                "job_id": job_id,
                "character_count": transcription_result.get("character_count"),
                "segment_count": transcription_result.get("segment_count")
            })

            # Step 2: Create semantic chunks (Ollama topic analysis)
            logger.info("Step 2: Creating semantic chunks", extra={"job_id": job_id})

            # Pass only job_id - the activity will fetch transcript/segments from DB
            # This avoids passing large payloads through Temporal
            chunking_input = {
                "job_id": job_id
            }

            chunking_result = await workflow.execute_activity(
                "chunk_with_ollama_activity",
                chunking_input,
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=2),  # Less retries (expensive)
            )

            logger.info("Chunking completed", extra={
                "job_id": job_id,
                "chunk_count": chunking_result.get("chunk_count"),
                "chunking_method": chunking_result.get("chunking_method")
            })

            # Step 3: Generate and store embeddings for chunks
            logger.info("Step 3: Generating embeddings", extra={"job_id": job_id})

            # Pass only job_id - the activity will load chunks from DB
            # This avoids passing large chunk data through Temporal event history
            embedding_input = {
                "job_id": job_id
            }

            embedding_result = await workflow.execute_activity(
                "embed_chunks_activity",
                embedding_input,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            logger.info("Workflow completed successfully", extra={
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "chunk_count": chunking_result.get("chunk_count"),
                "embedding_count": embedding_result.get("embedding_count")
            })

            # Return minimal summary (avoid event history bloat)
            return {
                "job_id": job_id,
                "success": True,
                "chunk_count": chunking_result.get("chunk_count", 0),
                "chunking_method": chunking_result.get("chunking_method", "unknown")
            }

        except Exception as e:
            logger.error("Transcription workflow failed", extra={
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            raise