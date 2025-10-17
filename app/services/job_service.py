"""
Job management services for MxWhisper
"""
import os
import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.config import settings
from app.data import Job
from app.services.user_service import UserService
from app.workflows.transcribe.workflow import TranscribeWorkflow

logger = logging.getLogger(__name__)


class JobService:
    @staticmethod
    async def create_job(db: AsyncSession, filename: str, file_content: bytes, user_info: dict = None) -> Job:
        logger.info("Creating new job", extra={
            "file_filename": filename,
            "file_size": len(file_content),
            "has_user_info": user_info is not None
        })

        # Create uploads directory
        os.makedirs(settings.upload_dir, exist_ok=True)

        # Generate unique filename
        file_path = os.path.join(settings.upload_dir, f"{uuid.uuid4()}_{filename}")
        logger.debug("Generated file path", extra={
            "original_filename": filename,
            "file_path": file_path
        })

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)
        logger.debug("File saved to disk", extra={
            "file_path": file_path,
            "file_size": len(file_content)
        })

        # Create or update user if authenticated
        user_id = None
        if user_info:
            user = await UserService.create_or_update_user(db, user_info)
            user_id = user.id if user else None
            logger.debug("User processed for job", extra={
                "user_id": user_id,
                "username": user.preferred_username if user else None
            })

        # Create job in database
        job = Job(filename=filename, file_path=file_path, status="pending", user_id=user_id)
        db.add(job)
        await db.commit()
        await db.refresh(job)

        logger.info("Job created successfully", extra={
            "job_id": job.id,
            "file_filename": job.filename,
            "file_path": job.file_path,
            "user_id": job.user_id,
            "status": job.status
        })

        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str) -> Job:
        logger.debug("Retrieving job", extra={"job_id": job_id})
        try:
            job_id_int = int(job_id)
        except ValueError:
            logger.warning("Invalid job ID format in service", extra={"job_id": job_id})
            return None
        job = await db.get(Job, job_id_int)
        if job:
            logger.debug("Job found", extra={
                "job_id": job.id,
                "status": job.status,
                "file_filename": job.filename
            })
        else:
            logger.warning("Job not found", extra={"job_id": job_id})
        return job

    @staticmethod
    async def get_user_jobs(db: AsyncSession, user_id: str) -> list[Job]:
        """Get all jobs for a specific user."""
        result = await db.execute(select(Job).where(Job.user_id == user_id))
        return result.scalars().all()

    @staticmethod
    async def get_all_jobs(db: AsyncSession, user_id: str = None) -> list[Job]:
        """Get all jobs (admin only) or user's jobs."""
        from sqlalchemy import select
        if user_id and await UserService.is_admin(db, user_id):
            # Admin can see all jobs
            result = await db.execute(select(Job))
        else:
            # Regular users see only their jobs
            result = await db.execute(select(Job).where(Job.user_id == user_id))
        return result.scalars().all()

    @staticmethod
    async def trigger_workflow(job_id: int):
        try:
            client = await Client.connect(settings.temporal_host, namespace="default")
            await client.start_workflow(
                TranscribeWorkflow.run,
                job_id,
                id=f"transcribe-{job_id}",
                task_queue="transcribe",
            )
            logger.info("Workflow triggered successfully", extra={
                "job_id": job_id,
                "workflow_id": f"transcribe-{job_id}",
                "task_queue": "transcribe"
            })
        except Exception as e:
            logger.warning("Failed to trigger workflow", extra={
                "job_id": job_id,
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            logger.info("Job will remain in pending status until workflow is available", extra={
                "job_id": job_id
            })