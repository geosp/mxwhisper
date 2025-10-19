"""
Job-Topic Assignment API Endpoints
Endpoints for assigning topics to jobs and managing assignments
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.services.job_topic_service import JobTopicService
from app.schemas.job_topics import (
    JobTopicListResponse,
    JobTopicResponse,
    AssignTopicsRequest,
    AssignTopicsResponse,
    UpdateTopicReviewRequest,
    RemoveTopicResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["job-topics"])


@router.get("/{job_id}/topics", response_model=JobTopicListResponse)
async def get_job_topics(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Get all topics assigned to a job.

    Shows both AI-assigned and user-assigned topics.
    Includes confidence scores and reasoning for AI assignments.
    User must own the job.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        job_topics = await JobTopicService.get_job_topics(db, job_id)

        # Convert to response format
        topics = []
        for jt in job_topics:
            topics.append(JobTopicResponse(
                topic_id=jt.topic_id,
                name=jt.topic.name,
                ai_confidence=jt.ai_confidence,
                ai_reasoning=jt.ai_reasoning,
                assigned_by=jt.assigned_by,
                user_reviewed=jt.user_reviewed,
                assigned_at=jt.created_at
            ))

        return JobTopicListResponse(job_id=job_id, topics=topics)

    except Exception as e:
        logger.error(f"Error retrieving topics for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job topics"
        )


@router.post("/{job_id}/topics", response_model=AssignTopicsResponse)
async def assign_topics_to_job(
    job_id: int,
    request: AssignTopicsRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Assign topics to a job (user-initiated).

    Creates JobTopic records with assigned_by = current_user_id.
    Sets user_reviewed = true (manual assignment).
    Ignores duplicates (idempotent).
    User must own the job.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        job_topics = await JobTopicService.assign_topics_to_job(
            db, job_id, request.topic_ids, user_id
        )

        # Convert to response format
        assigned_topics = []
        for jt in job_topics:
            assigned_topics.append(JobTopicResponse(
                topic_id=jt.topic_id,
                name=jt.topic.name,
                ai_confidence=jt.ai_confidence,
                ai_reasoning=jt.ai_reasoning,
                assigned_by=jt.assigned_by,
                user_reviewed=jt.user_reviewed,
                assigned_at=jt.created_at
            ))

        return AssignTopicsResponse(
            job_id=job_id,
            assigned_topics=assigned_topics
        )

    except ValueError as e:
        logger.warning(f"Invalid topic assignment: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error assigning topics to job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign topics"
        )


@router.delete("/{job_id}/topics/{topic_id}", response_model=RemoveTopicResponse)
async def remove_topic_from_job(
    job_id: int,
    topic_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Remove a topic from a job.

    User must own the job.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        await JobTopicService.remove_topic_from_job(db, job_id, topic_id, user_id)

        return RemoveTopicResponse(
            message="Topic removed from job",
            job_id=job_id,
            topic_id=topic_id
        )

    except ValueError as e:
        logger.warning(f"Cannot remove topic: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error removing topic {topic_id} from job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove topic"
        )


@router.patch("/{job_id}/topics/{topic_id}", response_model=JobTopicResponse)
async def update_topic_review_status(
    job_id: int,
    topic_id: int,
    request: UpdateTopicReviewRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Update topic review status.

    Use case: User accepts/confirms an AI-suggested topic.
    Marks user_reviewed = true without removing the topic.
    User must own the job.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        job_topic = await JobTopicService.update_review_status(
            db, job_id, topic_id, user_id, request.user_reviewed
        )

        return JobTopicResponse(
            topic_id=job_topic.topic_id,
            name=job_topic.topic.name,
            ai_confidence=job_topic.ai_confidence,
            ai_reasoning=job_topic.ai_reasoning,
            assigned_by=job_topic.assigned_by,
            user_reviewed=job_topic.user_reviewed,
            assigned_at=job_topic.created_at
        )

    except ValueError as e:
        logger.warning(f"Cannot update review status: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating review status for topic {topic_id} on job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update review status"
        )
