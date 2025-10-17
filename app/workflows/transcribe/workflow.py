from datetime import timedelta
import logging

from temporalio import workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)

# Don't import transcribe_activity here to avoid heavy dependencies in workflow validation


@workflow.defn
class TranscribeWorkflow:
    @workflow.run
    async def run(self, job_id: int) -> dict:
        """
        Run transcription workflow.

        Returns:
            dict: Summary of transcription results (not the full transcript)
        """
        logger.info("Starting transcription workflow", extra={
            "job_id": job_id,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id
        })

        try:
            summary = await workflow.execute_activity(
                "transcribe_activity",  # Use string name instead of imported function
                job_id,
                start_to_close_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            logger.info("Transcription workflow completed successfully", extra={
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "summary": summary
            })
            return summary
        except Exception as e:
            logger.error("Transcription workflow failed", extra={
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            raise