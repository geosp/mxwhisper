#!/usr/bin/env python3
"""
Temporal Worker for MxWhisper transcription tasks
"""
import asyncio
import logging
from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from app.logging_config import setup_logging
from app.workflows.transcribe.activity import transcribe_activity
from app.workflows.transcribe.workflow import TranscribeWorkflow

# Setup logging
setup_logging(level="INFO", format_type="text", log_file="logs/mxwhisper-worker.log")

logger = logging.getLogger(__name__)

async def run_worker():
    """Run the Temporal worker for transcription tasks."""
    logger.info("Starting Temporal worker", extra={
        "temporal_host": settings.temporal_host,
        "namespace": "default",
        "task_queue": "transcribe"
    })

    client = await Client.connect(settings.temporal_host, namespace="default")

    worker = Worker(
        client,
        task_queue="transcribe",
        workflows=[TranscribeWorkflow],
        activities=[transcribe_activity],
    )

    logger.info("Worker started! Listening for transcription tasks...")
    await worker.run()

def main():
    """Main entry point for the CLI command."""
    asyncio.run(run_worker())

if __name__ == "__main__":
    main()