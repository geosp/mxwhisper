"""
Pydantic schemas for Job-Topic assignment endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class JobTopicResponse(BaseModel):
    """Schema for a job-topic assignment response"""
    topic_id: int
    name: str = Field(..., description="Topic name")
    ai_confidence: Optional[float] = Field(None, description="AI confidence score (0.0-1.0)")
    ai_reasoning: Optional[str] = Field(None, description="Why AI assigned this topic")
    assigned_by: Optional[str] = Field(None, description="User ID who assigned this topic (null if AI-assigned)")
    user_reviewed: bool = Field(False, description="Whether user has reviewed this assignment")
    assigned_at: datetime = Field(..., description="When the topic was assigned")

    class Config:
        from_attributes = True


class JobTopicListResponse(BaseModel):
    """Schema for list of job topics"""
    job_id: int
    topics: List[JobTopicResponse]


class AssignTopicsRequest(BaseModel):
    """Schema for assigning topics to a job"""
    topic_ids: List[int] = Field(..., min_length=1, description="List of topic IDs to assign")


class AssignTopicsResponse(BaseModel):
    """Schema for assign topics response"""
    job_id: int
    assigned_topics: List[JobTopicResponse]


class UpdateTopicReviewRequest(BaseModel):
    """Schema for updating topic review status"""
    user_reviewed: bool = Field(..., description="Mark topic as reviewed by user")


class RemoveTopicResponse(BaseModel):
    """Schema for topic removal response"""
    message: str
    job_id: int
    topic_id: int
