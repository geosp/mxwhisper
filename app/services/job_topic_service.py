"""
Job Topic Service - Business logic for job-topic assignments
"""
import logging
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.data.models import JobTopic, Job, Topic

logger = logging.getLogger(__name__)


class JobTopicService:
    """Service for managing job-topic assignments"""

    @staticmethod
    async def get_job_topics(db: AsyncSession, job_id: int) -> List[JobTopic]:
        """Get all topics assigned to a job"""
        result = await db.execute(
            select(JobTopic)
            .options(joinedload(JobTopic.topic))
            .where(JobTopic.job_id == job_id)
            .order_by(JobTopic.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def assign_topics_to_job(
        db: AsyncSession,
        job_id: int,
        topic_ids: List[int],
        user_id: str
    ) -> List[JobTopic]:
        """
        Assign multiple topics to a job (user-initiated assignment)
        Idempotent - ignores topics already assigned
        """
        logger.info(f"Assigning {len(topic_ids)} topics to job {job_id} by user {user_id}")

        # Verify job exists and user owns it
        job = await db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.user_id != user_id:
            raise PermissionError("You do not have permission to modify this job")

        # Verify all topics exist
        result = await db.execute(
            select(Topic).where(Topic.id.in_(topic_ids))
        )
        topics = result.scalars().all()
        found_topic_ids = {topic.id for topic in topics}

        missing_ids = set(topic_ids) - found_topic_ids
        if missing_ids:
            raise ValueError(f"Topics not found: {missing_ids}")

        # Get existing assignments
        existing_result = await db.execute(
            select(JobTopic)
            .where(JobTopic.job_id == job_id, JobTopic.topic_id.in_(topic_ids))
        )
        existing_assignments = existing_result.scalars().all()
        existing_topic_ids = {jt.topic_id for jt in existing_assignments}

        # Create new assignments for topics not already assigned
        new_assignments = []
        for topic_id in topic_ids:
            if topic_id not in existing_topic_ids:
                job_topic = JobTopic(
                    job_id=job_id,
                    topic_id=topic_id,
                    assigned_by=user_id,
                    user_reviewed=True,  # Manual assignment means reviewed
                    ai_confidence=None,  # Not AI-assigned
                    ai_reasoning=None
                )
                db.add(job_topic)
                new_assignments.append(job_topic)

        if new_assignments:
            await db.commit()
            # Refresh to get relationships
            for jt in new_assignments:
                await db.refresh(jt)

        logger.info(f"Created {len(new_assignments)} new topic assignments (skipped {len(existing_topic_ids)} existing)")

        # Return all assignments (existing + new)
        return await JobTopicService.get_job_topics(db, job_id)

    @staticmethod
    async def remove_topic_from_job(
        db: AsyncSession,
        job_id: int,
        topic_id: int,
        user_id: str
    ) -> bool:
        """Remove a topic assignment from a job"""
        logger.info(f"Removing topic {topic_id} from job {job_id}")

        # Verify job ownership
        job = await db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.user_id != user_id:
            raise PermissionError("You do not have permission to modify this job")

        # Get assignment
        result = await db.execute(
            select(JobTopic)
            .where(JobTopic.job_id == job_id, JobTopic.topic_id == topic_id)
        )
        job_topic = result.scalar_one_or_none()
        if not job_topic:
            raise ValueError(f"Topic {topic_id} is not assigned to job {job_id}")

        # Delete assignment
        await db.delete(job_topic)
        await db.commit()

        logger.info(f"Removed topic {topic_id} from job {job_id}")
        return True

    @staticmethod
    async def update_review_status(
        db: AsyncSession,
        job_id: int,
        topic_id: int,
        user_id: str,
        user_reviewed: bool
    ) -> JobTopic:
        """
        Update the review status of a topic assignment
        Used when user confirms/reviews an AI-suggested topic
        """
        logger.info(f"Updating review status for topic {topic_id} on job {job_id}")

        # Verify job ownership
        job = await db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.user_id != user_id:
            raise PermissionError("You do not have permission to modify this job")

        # Get assignment
        result = await db.execute(
            select(JobTopic)
            .where(JobTopic.job_id == job_id, JobTopic.topic_id == topic_id)
        )
        job_topic = result.scalar_one_or_none()
        if not job_topic:
            raise ValueError(f"Topic {topic_id} is not assigned to job {job_id}")

        # Update review status
        job_topic.user_reviewed = user_reviewed
        await db.commit()
        await db.refresh(job_topic)

        logger.info(f"Updated review status to {user_reviewed}")
        return job_topic

    @staticmethod
    async def get_jobs_needing_review(
        db: AsyncSession,
        user_id: str,
        limit: int = 100
    ) -> List[int]:
        """
        Get list of job IDs that have AI-assigned topics pending review
        """
        result = await db.execute(
            select(JobTopic.job_id.distinct())
            .join(Job, JobTopic.job_id == Job.id)
            .where(
                Job.user_id == user_id,
                JobTopic.user_reviewed == False,
                JobTopic.assigned_by == None  # AI-assigned (no user)
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def assign_topics_via_ai(
        db: AsyncSession,
        job_id: int,
        topic_assignments: List[dict]
    ) -> List[JobTopic]:
        """
        Assign topics to a job via AI categorization
        topic_assignments = [
            {"topic_id": 1, "confidence": 0.92, "reasoning": "..."},
            ...
        ]
        This is called from Phase 3 AI integration
        """
        logger.info(f"AI assigning {len(topic_assignments)} topics to job {job_id}")

        assignments = []
        for assignment in topic_assignments:
            job_topic = JobTopic(
                job_id=job_id,
                topic_id=assignment["topic_id"],
                ai_confidence=assignment.get("confidence"),
                ai_reasoning=assignment.get("reasoning"),
                assigned_by=None,  # AI-assigned
                user_reviewed=False
            )
            db.add(job_topic)
            assignments.append(job_topic)

        await db.commit()
        for jt in assignments:
            await db.refresh(jt)

        logger.info(f"AI assigned {len(assignments)} topics to job {job_id}")
        return assignments
