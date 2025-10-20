"""
TranscribeWorkflow Updated for media sourcing architecture.
Works with AudioFile and Transcription models.
"""
from datetime import timedelta
import logging
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)


@workflow.defn
class TranscribeWorkflow:
    """
    Workflow for transcribing audio files (new architecture).
    Works with pre-existing AudioFile and creates Transcription record.
    """

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run complete transcription workflow with semantic chunking.

        Workflow steps:
        1. Transcribe audio with Whisper → update Transcription
        2. Analyze transcript and create semantic chunks → create TranscriptionChunks
        3. Generate and store embeddings for chunks

        Args:
            input_data: Dictionary with:
                - transcription_id: int - Transcription ID (already created)
                - job_id: int - Job ID for tracking

        Returns:
            dict: Minimal summary (chunk_count, success) to avoid event history bloat
        """
        transcription_id = input_data["transcription_id"]
        job_id = input_data["job_id"]

        logger.info("Starting transcription workflow ", extra={
            "transcription_id": transcription_id,
            "job_id": job_id,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id
        })

        try:
            # Step 1: Transcribe audio with Whisper
            logger.info("Step 1: Transcribing audio", extra={
                "transcription_id": transcription_id,
                "job_id": job_id
            })

            transcription_result = await workflow.execute_activity(
                "transcribe_activity",
                input_data,
                start_to_close_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            logger.info("Transcription completed", extra={
                "transcription_id": transcription_id,
                "character_count": transcription_result.get("character_count"),
                "segment_count": transcription_result.get("segment_count"),
                "language": transcription_result.get("language")
            })

            # Step 2: Create semantic chunks
            logger.info("Step 2: Creating semantic chunks", extra={
                "transcription_id": transcription_id
            })

            # Pass transcription_id
            chunking_input = {
                "transcription_id": transcription_id,
                "job_id": job_id
            }

            chunking_result = await workflow.execute_activity(
                "chunk_with_ollama_activity",
                chunking_input,
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            logger.info("Chunking completed", extra={
                "transcription_id": transcription_id,
                "chunk_count": chunking_result.get("chunk_count"),
                "chunking_method": chunking_result.get("chunking_method")
            })


            # Step 3: Assign topics to transcription
            logger.info("Step 3: Assigning topics to transcription", extra={
                "transcription_id": transcription_id
            })

            # You may need to pass user_id; for now, try to get it from input_data
            user_id = input_data.get("user_id")
            if not user_id:
                logger.warning("No user_id provided in input_data; topic assignment may fail.")

            topic_assignment_input = {
                "transcription_id": transcription_id,
                "user_id": user_id or "system"
            }

            topic_assignment_result = await workflow.execute_activity(
                "assign_topics_activity",
                topic_assignment_input,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            logger.info("Topic assignment completed", extra={
                "transcription_id": transcription_id,
                "assigned_topic_ids": topic_assignment_result.get("assigned_topic_ids")
            })

            # Step 4: Generate and store embeddings
            logger.info("Step 4: Generating embeddings", extra={
                "transcription_id": transcription_id
            })

            embedding_input = {
                "transcription_id": transcription_id,
                "job_id": job_id
            }

            embedding_result = await workflow.execute_activity(
                "embed_chunks_activity",
                embedding_input,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            logger.info("Workflow completed successfully ", extra={
                "transcription_id": transcription_id,
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "chunk_count": chunking_result.get("chunk_count"),
                "embedding_count": embedding_result.get("embedding_count")
            })

            # Return minimal summary
            return {
                "transcription_id": transcription_id,
                "job_id": job_id,
                "success": True,
                "chunk_count": chunking_result.get("chunk_count", 0),
                "chunking_method": chunking_result.get("chunking_method", "unknown"),
                "embedding_count": embedding_result.get("embedding_count", 0)
            }

        except Exception as e:
            logger.error("Transcription workflow failed ", extra={
                "transcription_id": transcription_id,
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            raise
