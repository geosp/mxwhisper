"""
DownloadAudioWorkflow - Downloads audio from URL using yt-dlp
"""
from datetime import timedelta
import logging
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)


@workflow.defn
class DownloadAudioWorkflow:
    """
    Workflow for downloading audio from URLs.
    Separate from transcription workflow - user manually triggers transcription after download.
    """

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Download audio from URL and create AudioFile record.

        Workflow steps:
        1. Validate URL
        2. Download audio using yt-dlp
        3. Calculate checksum and check for duplicates
        4. Move to user folder and create AudioFile record

        Args:
            input_data: Dictionary with:
                - job_id: int - Job ID for tracking
                - user_id: str - User's ID
                - source_url: str - URL to download from

        Returns:
            Dictionary with:
                - audio_file_id: int
                - checksum: str
                - file_path: str
                - is_duplicate: bool
                - platform: str
        """
        job_id = input_data["job_id"]
        user_id = input_data["user_id"]
        source_url = input_data["source_url"]

        logger.info("Starting download workflow", extra={
            "job_id": job_id,
            "user_id": user_id,
            "source_url": source_url,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id
        })

        try:
            # Download audio using yt-dlp and create AudioFile record
            download_result = await workflow.execute_activity(
                "download_audio_activity",
                input_data,
                start_to_close_timeout=timedelta(minutes=30),  # Allow time for large downloads
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(seconds=60),
                    backoff_coefficient=2.0
                ),
            )

            logger.info("Download workflow completed successfully", extra={
                "job_id": job_id,
                "workflow_id": workflow.info().workflow_id,
                "audio_file_id": download_result["audio_file_id"],
                "is_duplicate": download_result["is_duplicate"],
                "platform": download_result["platform"]
            })

            return {
                "job_id": job_id,
                "success": True,
                "audio_file_id": download_result["audio_file_id"],
                "checksum": download_result["checksum"],
                "is_duplicate": download_result["is_duplicate"],
                "platform": download_result["platform"]
            }

        except Exception as e:
            logger.error("Download workflow failed", extra={
                "job_id": job_id,
                "user_id": user_id,
                "source_url": source_url,
                "workflow_id": workflow.info().workflow_id,
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            raise
