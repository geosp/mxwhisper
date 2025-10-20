"""
Pydantic schemas for transcription endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# Request schemas

class TranscribeRequest(BaseModel):
    """Request to create transcription from audio file"""
    model: Optional[str] = Field("whisper-large-v3", description="Whisper model to use")
    language: Optional[str] = Field(None, description="Force specific language (e.g., 'en')")


class AssignTopicsToTranscriptionRequest(BaseModel):
    """Request to assign topics to transcription"""
    topic_ids: List[int] = Field(..., description="List of topic IDs to assign")


class AddTranscriptionToCollectionRequest(BaseModel):
    """Request to add transcription to collection"""
    collection_id: int
    position: Optional[int] = Field(None, description="Position in collection")


# Response schemas

class TranscriptionChunkResponse(BaseModel):
    """Response for transcription chunk"""
    id: int
    chunk_index: int
    text: str
    topic_summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    confidence: Optional[float] = None
    start_time: Optional[float] = Field(None, description="Start time in seconds")
    end_time: Optional[float] = Field(None, description="End time in seconds")
    start_char_pos: Optional[int] = None
    end_char_pos: Optional[int] = None

    class Config:
        from_attributes = True


class TranscriptionTopicResponse(BaseModel):
    """Response for transcription topic assignment"""
    id: int
    name: str
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None
    user_reviewed: bool = False


class TranscriptionCollectionResponse(BaseModel):
    """Response for transcription collection assignment"""
    id: int
    name: str
    position: Optional[int] = None
    collection_type: Optional[str] = None


class AudioFileSummaryResponse(BaseModel):
    """Summary of audio file for transcription responses"""
    id: int
    filename: str
    duration: Optional[float] = None
    source_type: str


class TranscriptionSummaryResponse(BaseModel):
    """Summary response for transcription (for lists)"""
    id: int
    audio_file_id: int
    status: str
    language: Optional[str] = None
    avg_confidence: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TranscriptionResponse(BaseModel):
    """Response for transcription details"""
    id: int
    audio_file_id: int
    user_id: str
    transcript: str = Field(..., description="Full transcript text")
    language: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    avg_confidence: Optional[float] = None
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    status: str = Field(..., description="'pending', 'processing', 'completed', or 'failed'")
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Related data
    audio_file: Optional[AudioFileSummaryResponse] = None
    topics: List[TranscriptionTopicResponse] = Field(default_factory=list)
    collections: List[TranscriptionCollectionResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TranscriptionDetailResponse(TranscriptionResponse):
    """Detailed transcription response with chunks"""
    chunks: List[TranscriptionChunkResponse] = Field(default_factory=list)


class TranscriptionListResponse(BaseModel):
    """Response for paginated transcription list"""
    total: int
    limit: int
    offset: int
    transcriptions: List[TranscriptionResponse]


class TranscriptionCreateResponse(BaseModel):
    """Response for transcription creation (returns job info)"""
    job_id: int
    transcription_id: int
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Status message")


class TranscriptionDeleteResponse(BaseModel):
    """Response for transcription deletion"""
    message: str
