"""
Pydantic schemas for audio file endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


# Request schemas

class AudioFileDownloadRequest(BaseModel):
    """Request to download audio from URL"""
    source_url: str = Field(..., description="URL to download audio from")


# Response schemas

class AudioFileResponse(BaseModel):
    """Response for audio file details"""
    id: int
    user_id: str
    file_path: str
    original_filename: str
    file_size: int = Field(..., description="File size in bytes")
    mime_type: Optional[str] = None
    duration: Optional[float] = Field(None, description="Duration in seconds")
    checksum: str
    source_type: str = Field(..., description="'upload' or 'download'")
    source_url: Optional[str] = None
    source_platform: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Count of related transcriptions (optional, for list views)
    transcription_count: Optional[int] = None

    class Config:
        from_attributes = True


class AudioFileUploadResponse(BaseModel):
    """Response for audio file upload"""
    audio_file_id: int
    filename: str
    file_size: int = Field(..., description="File size in bytes")
    duration: Optional[float] = Field(None, description="Duration in seconds")
    checksum: str
    is_duplicate: bool = Field(..., description="True if file already existed")
    created_at: datetime
    message: Optional[str] = Field(None, description="Additional message")


class AudioFileListResponse(BaseModel):
    """Response for paginated audio file list"""
    total: int
    limit: int
    offset: int
    audio_files: List[AudioFileResponse]


class AudioFileDetailResponse(AudioFileResponse):
    """Detailed audio file response with related transcriptions"""
    transcriptions: List["TranscriptionSummaryResponse"] = Field(default_factory=list)


class AudioFileDeleteResponse(BaseModel):
    """Response for audio file deletion"""
    message: str
    deleted_transcriptions: int = Field(..., description="Number of transcriptions deleted")


# Import TranscriptionSummaryResponse for forward reference
from app.schemas.transcriptions import TranscriptionSummaryResponse

# Rebuild model to resolve forward references
AudioFileDetailResponse.model_rebuild()
