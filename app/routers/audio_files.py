"""
Audio File Management API Endpoints
Upload local files or download from URLs
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.data.models import Job
from app.config import settings
from app.services.audio_file_service import AudioFileService
from app.schemas.audio_files import (
    AudioFileDownloadRequest,
    AudioFileResponse,
    AudioFileUploadResponse,
    AudioFileListResponse,
    AudioFileDetailResponse,
    AudioFileDeleteResponse,
)
from app.workflows.download.workflow import DownloadAudioWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/upload", response_model=AudioFileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio_file(
    file: UploadFile = File(..., description="Audio file to upload"),
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Upload a local audio file.

    Creates AudioFile record with deduplication.
    If duplicate exists, returns existing record with is_duplicate=true.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Create audio file record (handles deduplication)
        audio_file, is_duplicate = await AudioFileService.create_from_upload(
            db, user_id, file
        )

        message = None
        if is_duplicate:
            message = "File already exists. Returning existing record."

        return AudioFileUploadResponse(
            audio_file_id=audio_file.id,
            filename=audio_file.original_filename,
            file_size=audio_file.file_size,
            duration=audio_file.duration,
            checksum=audio_file.checksum,
            is_duplicate=is_duplicate,
            created_at=audio_file.created_at,
            message=message
        )

    except Exception as e:
        logger.error(f"Error uploading audio file for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload audio file"
        )


@router.post("/download", status_code=status.HTTP_202_ACCEPTED)
async def download_audio_from_url(
    request: AudioFileDownloadRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Download audio from URL using yt-dlp.

    Creates a Job and starts DownloadAudioWorkflow asynchronously.
    Returns job_id for tracking progress.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Create job for tracking
        job = Job(
            user_id=user_id,
            filename=f"Download: {request.source_url}",
            file_path="",  # Will be set by workflow
            status="pending"
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        logger.info("Created download job", extra={
            "job_id": job.id,
            "user_id": user_id,
            "source_url": request.source_url
        })

        # Start Temporal workflow
        try:
            client = await Client.connect(settings.temporal_host, namespace="default")
            await client.start_workflow(
                DownloadAudioWorkflow.run,
                {
                    "job_id": job.id,
                    "user_id": user_id,
                    "source_url": request.source_url
                },
                id=f"download-{job.id}",
                task_queue="download",
            )
            logger.info("Download workflow started", extra={
                "job_id": job.id,
                "workflow_id": f"download-{job.id}"
            })

        except Exception as e:
            logger.error(f"Failed to start download workflow: {e}", exc_info=True)
            # Update job status to failed
            job.status = "failed"
            job.error = f"Failed to start workflow: {str(e)}"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start download workflow"
            )

        return {
            "job_id": job.id,
            "status": "pending",
            "message": "Download started. Use /jobs/{job_id} to track progress."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating download job for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create download job"
        )


@router.get("", response_model=AudioFileListResponse)
async def list_audio_files(
    source_type: Optional[str] = Query(None, description="Filter by source type (upload/download)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    List user's audio files with pagination.

    Returns audio files ordered by created_at (newest first).
    Can filter by source_type.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Get audio files
        audio_files = await AudioFileService.get_user_files(
            db, user_id, source_type, limit, offset
        )

        # Get total count
        total = await AudioFileService.count_user_files(db, user_id, source_type)

        # Convert to response models
        audio_file_responses = []
        for audio_file in audio_files:
            # Get transcription count
            from sqlalchemy import select, func
            from app.data.models import Transcription

            result = await db.execute(
                select(func.count(Transcription.id)).where(
                    Transcription.audio_file_id == audio_file.id
                )
            )
            transcription_count = result.scalar_one()

            response = AudioFileResponse.model_validate(audio_file)
            response.transcription_count = transcription_count
            audio_file_responses.append(response)

        return AudioFileListResponse(
            total=total,
            limit=limit,
            offset=offset,
            audio_files=audio_file_responses
        )

    except Exception as e:
        logger.error(f"Error listing audio files for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audio files"
        )


@router.get("/{audio_file_id}", response_model=AudioFileDetailResponse)
async def get_audio_file(
    audio_file_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Get detailed audio file information.

    Returns audio file with list of related transcriptions.
    User must own the file.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        audio_file = await AudioFileService.get_by_id(db, audio_file_id)
        if not audio_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
            )

        # Permission check
        if audio_file.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this audio file"
            )

        # Get related transcriptions
        from sqlalchemy import select
        from app.data.models import Transcription
        from app.schemas.transcriptions import TranscriptionSummaryResponse

        result = await db.execute(
            select(Transcription).where(
                Transcription.audio_file_id == audio_file_id
            ).order_by(Transcription.created_at.desc())
        )
        transcriptions = result.scalars().all()

        # Convert to response
        transcription_responses = [
            TranscriptionSummaryResponse.model_validate(t) for t in transcriptions
        ]

        # Create response using AudioFileResponse first to avoid relationship loading issues
        audio_file_response = AudioFileResponse.model_validate(audio_file)
        data = audio_file_response.model_dump()
        data['transcriptions'] = transcription_responses
        response_data = AudioFileDetailResponse.model_validate(data)

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audio file {audio_file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audio file"
        )


@router.delete("/{audio_file_id}", response_model=AudioFileDeleteResponse)
async def delete_audio_file(
    audio_file_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Delete audio file and all related transcriptions.

    User must own the file.
    Cascade deletes transcriptions and chunks via FK constraints.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Get file to count transcriptions before deletion
        audio_file = await AudioFileService.get_by_id(db, audio_file_id)
        if not audio_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
            )

        # Permission check
        if audio_file.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this audio file"
            )

        # Count transcriptions
        from sqlalchemy import select, func
        from app.data.models import Transcription

        result = await db.execute(
            select(func.count(Transcription.id)).where(
                Transcription.audio_file_id == audio_file_id
            )
        )
        transcription_count = result.scalar_one()

        # Delete file (cascades to transcriptions)
        success = await AudioFileService.delete_file(db, audio_file_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete audio file"
            )

        return AudioFileDeleteResponse(
            message=f"Audio file deleted successfully",
            deleted_transcriptions=transcription_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting audio file {audio_file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete audio file"
        )
