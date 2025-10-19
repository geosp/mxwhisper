"""
Job-Collection Assignment API Endpoints
Endpoints for adding jobs to collections and managing positions
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.services.collection_service import CollectionService
from app.schemas.job_collections import (
    JobCollectionListResponse,
    JobCollectionResponse,
    AddToCollectionRequest,
    AddToCollectionResponse,
    UpdatePositionRequest,
    RemoveFromCollectionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["job-collections"])


@router.get("/{job_id}/collections", response_model=JobCollectionListResponse)
async def get_job_collections(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Get all collections containing this job.

    Shows collection name, position, and when added.
    User must own the job.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        from sqlalchemy import select
        from app.data.models import JobCollection, Collection

        # Get job collections with collection details
        result = await db.execute(
            select(JobCollection, Collection)
            .join(Collection, JobCollection.collection_id == Collection.id)
            .where(JobCollection.job_id == job_id)
            .order_by(Collection.name)
        )

        collections = []
        for job_collection, collection in result:
            collections.append(JobCollectionResponse(
                collection_id=collection.id,
                name=collection.name,
                position=job_collection.position,
                assigned_at=job_collection.created_at
            ))

        return JobCollectionListResponse(job_id=job_id, collections=collections)

    except Exception as e:
        logger.error(f"Error retrieving collections for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job collections"
        )


@router.post("/{job_id}/collections", response_model=AddToCollectionResponse, status_code=status.HTTP_201_CREATED)
async def add_job_to_collection(
    job_id: int,
    request: AddToCollectionRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Add a job to a collection.

    User must own both the collection and the job.
    Position is optional (auto-increments if not provided).
    Validates that job and collection exist and are owned by user.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        job_collection = await CollectionService.add_job_to_collection(
            db, job_id, request.collection_id, user_id, request.position
        )

        return AddToCollectionResponse(
            job_id=job_id,
            collection_id=request.collection_id,
            position=job_collection.position,
            assigned_by=user_id,
            created_at=job_collection.created_at
        )

    except ValueError as e:
        logger.warning(f"Invalid job-collection assignment: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error adding job {job_id} to collection {request.collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add job to collection"
        )


@router.patch("/{job_id}/collections/{collection_id}", response_model=AddToCollectionResponse)
async def update_job_position_in_collection(
    job_id: int,
    collection_id: int,
    request: UpdatePositionRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Update job position within a collection.

    Use case: Reorder jobs within a collection (e.g., reorder book chapters).
    User must own the collection.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        job_collection = await CollectionService.update_job_position(
            db, job_id, collection_id, user_id, request.position
        )

        return AddToCollectionResponse(
            job_id=job_id,
            collection_id=collection_id,
            position=job_collection.position,
            assigned_by=job_collection.assigned_by,
            created_at=job_collection.created_at
        )

    except ValueError as e:
        logger.warning(f"Cannot update position: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating position for job {job_id} in collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update position"
        )


@router.delete("/{job_id}/collections/{collection_id}", response_model=RemoveFromCollectionResponse)
async def remove_job_from_collection(
    job_id: int,
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Remove a job from a collection.

    User must own the collection.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        await CollectionService.remove_job_from_collection(
            db, job_id, collection_id, user_id
        )

        return RemoveFromCollectionResponse(
            message="Job removed from collection",
            job_id=job_id,
            collection_id=collection_id
        )

    except ValueError as e:
        logger.warning(f"Cannot remove job from collection: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error removing job {job_id} from collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove job from collection"
        )
