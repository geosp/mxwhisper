"""
Topic Management API Endpoints
Admin-only topic CRUD operations
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.services.user_service import UserService
from app.services.topic_service import TopicService
from app.schemas.topics import (
    TopicCreate,
    TopicUpdate,
    TopicResponse,
    TopicListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
async def list_topics(
    db: AsyncSession = Depends(get_db)
):
    """
    List all topics in hierarchical structure.
    Public endpoint - no authentication required.

    Returns nested structure with root topics containing their children.
    """
    try:
        # Get all topics
        topics = await TopicService.get_all_topics(db)

        # Build hierarchy
        hierarchical_topics = await TopicService.build_topic_hierarchy(topics)

        return TopicListResponse(topics=hierarchical_topics)

    except Exception as e:
        logger.error(f"Error listing topics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve topics"
        )


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    topic_data: TopicCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Create a new topic (Admin only).

    Requires admin role.
    Topic name must be unique.
    If parent_id provided, parent topic must exist.
    """
    # Check admin permission
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        topic = await TopicService.create_topic(db, topic_data)
        return TopicResponse.model_validate(topic)

    except ValueError as e:
        logger.warning(f"Invalid topic creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating topic: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create topic"
        )


@router.put("/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: int,
    topic_data: TopicUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Update an existing topic (Admin only).

    Requires admin role.
    Cannot create circular parent references.
    Name must remain unique.
    """
    # Check admin permission
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        topic = await TopicService.update_topic(db, topic_id, topic_data)
        return TopicResponse.model_validate(topic)

    except ValueError as e:
        logger.warning(f"Invalid topic update: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating topic {topic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update topic"
        )


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Delete a topic (Admin only).

    Requires admin role.
    Cannot delete if topic has children - must delete or reassign children first.
    Cascade deletes job_topics associations.
    """
    # Check admin permission
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        await TopicService.delete_topic(db, topic_id)
        return None  # 204 No Content

    except ValueError as e:
        logger.warning(f"Cannot delete topic {topic_id}: {e}")
        if "has" in str(e) and "child" in str(e):
            # Topic has children
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting topic {topic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete topic"
        )


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a single topic by ID.
    Public endpoint - no authentication required.
    """
    try:
        topic = await TopicService.get_topic_by_id(db, topic_id)
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Topic {topic_id} not found"
            )

        return TopicResponse.model_validate(topic)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving topic {topic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve topic"
        )
