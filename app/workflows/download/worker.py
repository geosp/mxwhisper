#!/usr/bin/env python3
"""
Temporal Worker for MxWhisper download tasks
"""
import asyncio
import logging
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from app.config import settings
from app.logging_config import setup_logging
from app.workflows.download.activities.download import download_audio_activity
from app.workflows.download.workflow import DownloadAudioWorkflow

# Setup logging
setup_logging(level="INFO", format_type="text", log_file="logs/mxwhisper-download-worker.log")

logger = logging.getLogger(__name__)

async def run_worker():
    """Run the Temporal worker for download tasks."""
    logger.info("Starting Temporal download worker", extra={
        "temporal_host": settings.temporal_host,
        "namespace": "default",
        "task_queue": "download"
    })

    client = await Client.connect(settings.temporal_host, namespace="default")

    # Configure sandbox to allow config and activity imports
    # Mark modules that should not be sandboxed (safe for deterministic use)
    # These modules are only used in activities, not in workflow logic
    workflow_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            "app.config",
            "app.logging_config",
            "app.data",
            "app.data.models",
            "app.data.database",
            "app.services",
            "app.services.audio_file_service",
            "app.services.download_service",
            "app.services.websocket_manager",
            "app.services.transcription_service",
            "app.services.embedding_service",
            "app.workflows.transcribe",
            "app.workflows.transcribe.activities",
            "app.workflows.transcribe.services",
            "app.workflows.transcribe.services.whisper_service",
            "app.workflows.transcribe.services.ollama_service",
            "app.workflows.transcribe.utils",
            "app.workflows.transcribe.utils.heartbeat",
            "pydantic",
            "pydantic_settings",
            "sqlalchemy",
            "pgvector",
            "redis",
            "httpx",
            "yt_dlp",
            "whisper",
            "torch",
            "sentence_transformers",
            "transformers",
            "numpy",
        )
    )

    worker = Worker(
        client,
        task_queue="download",
        workflows=[DownloadAudioWorkflow],
        activities=[
            download_audio_activity,
        ],
        workflow_runner=workflow_runner,
    )

    logger.info("Download worker started! Listening for download tasks...")
    await worker.run()

def main():
    """Main entry point for the CLI command."""
    asyncio.run(run_worker())

if __name__ == "__main__":
    main()
