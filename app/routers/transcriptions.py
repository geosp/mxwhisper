"""
Transcription Management API Endpoints
Create and manage transcriptions for audio files
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from temporalio.client import Client

from app.data.database import get_db
from app.auth.jwt import verify_token
from app.data.models import AudioFile, Transcription, TranscriptionChunk, Job
from app.config import settings
from app.services.transcription_service import TranscriptionService
from app.services.audio_file_service import AudioFileService
from app.schemas.transcriptions import (
    TranscribeRequest,
    TranscriptionResponse,
    TranscriptionDetailResponse,
    TranscriptionListResponse,
    TranscriptionCreateResponse,
    TranscriptionDeleteResponse,
    AudioFileSummaryResponse,
    TranscriptionChunkResponse,
)
from app.workflows.transcribe.workflow import TranscribeWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


@router.post("/{audio_file_id}/transcribe", response_model=TranscriptionCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_transcription(
    audio_file_id: int,
    request: TranscribeRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Create a new transcription for an audio file.

    Creates a Job and Transcription record, then starts TranscribeWorkflow asynchronously.
    Returns job_id and transcription_id for tracking progress.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Get audio file and verify ownership
        audio_file = await AudioFileService.get_by_id(db, audio_file_id)
        if not audio_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
            )

        if audio_file.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to transcribe this audio file"
            )

        # Create job for tracking
        job = Job(
            user_id=user_id,
            filename=f"Transcribe: {audio_file.original_filename}",
            file_path=audio_file.file_path,
            status="pending"
        )
        db.add(job)
        await db.flush()

        # Create transcription record
        transcription = await TranscriptionService.create_transcription(
            db=db,
            audio_file_id=audio_file_id,
            user_id=user_id,
            model_name=request.model,
            language=request.language
        )

        await db.commit()
        await db.refresh(job)
        await db.refresh(transcription)

        logger.info("Created transcription job", extra={
            "job_id": job.id,
            "transcription_id": transcription.id,
            "audio_file_id": audio_file_id,
            "user_id": user_id,
            "model": request.model
        })

        # Start Temporal workflow
        try:
            client = await Client.connect(settings.temporal_host, namespace="default")
            await client.start_workflow(
                TranscribeWorkflow.run,
                {
                    "transcription_id": transcription.id,
                    "job_id": job.id
                },
                id=f"transcribe-{job.id}",
                task_queue="transcribe",
            )
            logger.info("Transcribe workflow started", extra={
                "job_id": job.id,
                "transcription_id": transcription.id,
                "workflow_id": f"transcribe-{job.id}"
            })

        except Exception as e:
            logger.error(f"Failed to start transcribe workflow: {e}", exc_info=True)
            # Update job and transcription status to failed
            job.status = "failed"
            job.error = f"Failed to start workflow: {str(e)}"
            transcription.status = "failed"
            transcription.error_message = f"Failed to start workflow: {str(e)}"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start transcription workflow"
            )

        return TranscriptionCreateResponse(
            job_id=job.id,
            transcription_id=transcription.id,
            status="pending",
            message="Transcription started. Use /jobs/{job_id} or /transcriptions/{transcription_id} to track progress."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating transcription for audio file {audio_file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create transcription"
        )


@router.get("", response_model=TranscriptionListResponse)
async def list_transcriptions(
    audio_file_id: Optional[int] = Query(None, description="Filter by audio file ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    List user's transcriptions with pagination.

    Returns transcriptions ordered by created_at (newest first).
    Can filter by audio_file_id and status.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        # Build query
        query = select(Transcription).where(Transcription.user_id == user_id)

        if audio_file_id:
            query = query.where(Transcription.audio_file_id == audio_file_id)

        if status_filter:
            query = query.where(Transcription.status == status_filter)

        # Get total count
        count_query = select(func.count(Transcription.id)).where(Transcription.user_id == user_id)
        if audio_file_id:
            count_query = count_query.where(Transcription.audio_file_id == audio_file_id)
        if status_filter:
            count_query = count_query.where(Transcription.status == status_filter)

        result = await db.execute(count_query)
        total = result.scalar_one()

        # Get transcriptions
        query = query.order_by(Transcription.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        transcriptions = result.scalars().all()

        # Convert to response models
        transcription_responses = []
        for transcription in transcriptions:
            # Get audio file info
            audio_file = await AudioFileService.get_by_id(db, transcription.audio_file_id)
            audio_file_summary = None
            if audio_file:
                audio_file_summary = AudioFileSummaryResponse(
                    id=audio_file.id,
                    filename=audio_file.original_filename,
                    duration=audio_file.duration,
                    source_type=audio_file.source_type
                )

            response = TranscriptionResponse.model_validate(transcription)
            response.audio_file = audio_file_summary
            transcription_responses.append(response)

        return TranscriptionListResponse(
            total=total,
            limit=limit,
            offset=offset,
            transcriptions=transcription_responses
        )

    except Exception as e:
        logger.error(f"Error listing transcriptions for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transcriptions"
        )


@router.get("/{transcription_id}", response_model=TranscriptionDetailResponse)
async def get_transcription(
    transcription_id: int,
    include_chunks: bool = Query(True, description="Include transcription chunks"),
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Get detailed transcription information.

    Returns transcription with full transcript and optional chunks.
    User must own the transcription.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        transcription = await TranscriptionService.get_by_id(db, transcription_id)
        if not transcription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transcription not found"
            )

        # Permission check
        if transcription.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this transcription"
            )

        # Get audio file info
        audio_file = await AudioFileService.get_by_id(db, transcription.audio_file_id)
        audio_file_summary = None
        if audio_file:
            audio_file_summary = AudioFileSummaryResponse(
                id=audio_file.id,
                filename=audio_file.original_filename,
                duration=audio_file.duration,
                source_type=audio_file.source_type
            )

        # Get chunks if requested
        chunks = []
        if include_chunks:
            result = await db.execute(
                select(TranscriptionChunk).where(
                    TranscriptionChunk.transcription_id == transcription_id
                ).order_by(TranscriptionChunk.chunk_index)
            )
            chunk_records = result.scalars().all()
            chunks = [TranscriptionChunkResponse.model_validate(c) for c in chunk_records]

        # Build response
        transcription_dict = {
            'id': transcription.id,
            'audio_file_id': transcription.audio_file_id,
            'user_id': transcription.user_id,
            'transcript': transcription.transcript,
            'language': transcription.language,
            'model_name': transcription.model_name,
            'model_version': transcription.model_version,
            'avg_confidence': transcription.avg_confidence,
            'processing_time': transcription.processing_time,
            'status': transcription.status,
            'error_message': transcription.error_message,
            'created_at': transcription.created_at,
            'updated_at': transcription.updated_at,
            'audio_file': audio_file_summary,
            'topics': [],  # TODO: Add topics if needed
            'collections': [],  # TODO: Add collections if needed
            'chunks': chunks
        }
        response = TranscriptionDetailResponse.model_validate(transcription_dict)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transcription"
        )


@router.delete("/{transcription_id}", response_model=TranscriptionDeleteResponse)
async def delete_transcription(
    transcription_id: int,
    db: AsyncSession = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """
    Delete a transcription and all related chunks.

    User must own the transcription.
    Does not delete the audio file (use DELETE /audio/{id} for that).
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    try:
        transcription = await TranscriptionService.get_by_id(db, transcription_id)
        if not transcription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transcription not found"
            )

        # Permission check
        if transcription.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this transcription"
            )

        # Delete transcription (cascades to chunks)
        await db.delete(transcription)
        await db.commit()

        logger.info("Transcription deleted", extra={
            "transcription_id": transcription_id,
            "user_id": user_id
        })

        return TranscriptionDeleteResponse(
            message="Transcription deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete transcription"
        )
