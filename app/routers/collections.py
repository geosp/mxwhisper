"""
Collection Management API Endpoints
User-owned collection CRUD operations
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.services.collection_service import CollectionService
from app.schemas.collections import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionDetailResponse,
    CollectionListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    collection_type: Optional[str] = Query(None, description="Filter by collection type"),
    is_public: Optional[bool] = Query(None, description="Filter by public/private"),
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    List user's collections with optional filters.

    Returns only collections owned by the current user.
    Can filter by collection_type and is_public.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        collections = await CollectionService.get_user_collections(
            db, user_id, collection_type, is_public
        )

        # Add job counts
        collection_responses = []
        for collection in collections:
            job_count = await CollectionService.get_collection_job_count(db, collection.id)
            collection_data = CollectionResponse.model_validate(collection)
            collection_data.job_count = job_count
            collection_responses.append(collection_data)

        return CollectionListResponse(collections=collection_responses)

    except Exception as e:
        logger.error(f"Error listing collections for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve collections"
        )


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Get collection details with list of jobs.

    User must own the collection OR collection must be public.
    Returns jobs ordered by position.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        collection = await CollectionService.get_collection_by_id(db, collection_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found"
            )

        # Check access permission
        can_access = await CollectionService.can_access_collection(db, collection_id, user_id)
        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this collection"
            )

        # Get jobs in collection
        jobs = await CollectionService.get_collection_jobs(db, collection_id)

        # Build response
        response_data = {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "collection_type": collection.collection_type,
            "is_public": collection.is_public,
            "user_id": collection.user_id,
            "jobs": jobs,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
        }

        return CollectionDetailResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve collection"
        )


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    collection_data: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Create a new collection.

    Automatically sets user_id from auth token.
    Collection name is required (max 200 chars).
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        collection = await CollectionService.create_collection(
            db, user_id, collection_data
        )

        # Get job count (0 for new collection)
        response_data = CollectionResponse.model_validate(collection)
        response_data.job_count = 0

        return response_data

    except Exception as e:
        logger.error(f"Error creating collection for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create collection"
        )


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    collection_data: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Update an existing collection.

    User must own the collection.
    Can update name, description, type, and visibility.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        collection = await CollectionService.update_collection(
            db, collection_id, user_id, collection_data
        )

        # Get job count
        job_count = await CollectionService.get_collection_job_count(db, collection.id)
        response_data = CollectionResponse.model_validate(collection)
        response_data.job_count = job_count

        return response_data

    except ValueError as e:
        logger.warning(f"Invalid collection update: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update collection"
        )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Delete a collection.

    User must own the collection.
    Cascade deletes job_collections associations.
    Does NOT delete jobs themselves.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        await CollectionService.delete_collection(db, collection_id, user_id)
        return None  # 204 No Content

    except ValueError as e:
        logger.warning(f"Cannot delete collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete collection"
        )
