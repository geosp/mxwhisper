"""
Pydantic schemas for Topic endpoints
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TopicBase(BaseModel):
    """Base topic schema with common fields"""
    name: str = Field(..., min_length=1, max_length=100, description="Topic name")
    description: Optional[str] = Field(None, description="Topic description")
    parent_id: Optional[int] = Field(None, description="Parent topic ID for hierarchical organization")


class TopicCreate(TopicBase):
    """Schema for creating a new topic"""
    pass


class TopicUpdate(BaseModel):
    """Schema for updating an existing topic"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Topic name")
    description: Optional[str] = Field(None, description="Topic description")
    parent_id: Optional[int] = Field(None, description="Parent topic ID")


class TopicResponse(TopicBase):
    """Schema for topic response"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TopicWithChildren(TopicResponse):
    """Schema for topic with nested children (hierarchical view)"""
    children: List["TopicWithChildren"] = Field(default_factory=list, description="Child topics")

    class Config:
        from_attributes = True


class TopicListResponse(BaseModel):
    """Schema for list of topics"""
    topics: List[TopicWithChildren]


# Enable forward references for recursive model
TopicWithChildren.model_rebuild()
