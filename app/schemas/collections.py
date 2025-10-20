"""
Pydantic schemas for Collection endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CollectionBase(BaseModel):
    """Base collection schema with common fields"""
    name: str = Field(..., min_length=1, max_length=200, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    collection_type: Optional[str] = Field(None, max_length=50, description="Collection type (book, course, series, album, etc.)")
    is_public: bool = Field(False, description="Whether the collection is publicly visible")


class CollectionCreate(CollectionBase):
    """Schema for creating a new collection"""
    pass


class CollectionUpdate(BaseModel):
    """Schema for updating an existing collection"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    collection_type: Optional[str] = Field(None, max_length=50, description="Collection type")
    is_public: Optional[bool] = Field(None, description="Whether the collection is publicly visible")


class CollectionResponse(CollectionBase):
    """Schema for collection response"""
    id: int
    user_id: str
    job_count: int = Field(0, description="Number of jobs in this collection")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TranscriptionInCollection(BaseModel):
    """Schema for a transcription within a collection"""
    transcription_id: int
    position: Optional[int] = Field(None, description="Position/order within collection")
    language: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CollectionDetailResponse(CollectionBase):
    """Schema for detailed collection response with transcriptions"""
    id: int
    user_id: str
    transcriptions: List[TranscriptionInCollection] = Field(default_factory=list, description="Transcriptions in this collection")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CollectionListResponse(BaseModel):
    """Schema for list of collections"""
    collections: List[CollectionResponse]
