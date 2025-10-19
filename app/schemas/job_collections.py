"""
Pydantic schemas for Job-Collection assignment endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class JobCollectionResponse(BaseModel):
    """Schema for a job-collection assignment response"""
    collection_id: int
    name: str = Field(..., description="Collection name")
    position: Optional[int] = Field(None, description="Position/order within collection")
    assigned_at: datetime = Field(..., description="When added to collection")

    class Config:
        from_attributes = True


class JobCollectionListResponse(BaseModel):
    """Schema for list of job collections"""
    job_id: int
    collections: List[JobCollectionResponse]


class AddToCollectionRequest(BaseModel):
    """Schema for adding a job to a collection"""
    collection_id: int = Field(..., description="Collection ID to add job to")
    position: Optional[int] = Field(None, description="Position/order within collection (optional)")


class AddToCollectionResponse(BaseModel):
    """Schema for add to collection response"""
    job_id: int
    collection_id: int
    position: Optional[int]
    assigned_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class UpdatePositionRequest(BaseModel):
    """Schema for updating job position in collection"""
    position: int = Field(..., ge=1, description="New position within collection (1-indexed)")


class RemoveFromCollectionResponse(BaseModel):
    """Schema for removal from collection response"""
    message: str
    job_id: int
    collection_id: int
