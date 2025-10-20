"""
Pydantic schemas for request/response validation
"""
from .topics import (
    TopicBase,
    TopicCreate,
    TopicUpdate,
    TopicResponse,
    TopicWithChildren,
    TopicListResponse,
)
from .collections import (
    CollectionBase,
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionDetailResponse,
    CollectionListResponse,
)
from .job_topics import (
    JobTopicResponse,
    JobTopicListResponse,
    AssignTopicsRequest,
    UpdateTopicReviewRequest,
)
from .job_collections import (
    JobCollectionResponse,
    JobCollectionListResponse,
    AddToCollectionRequest,
    UpdatePositionRequest,
)
from .audio_files import (
    AudioFileDownloadRequest,
    AudioFileResponse,
    AudioFileUploadResponse,
    AudioFileListResponse,
    AudioFileDetailResponse,
    AudioFileDeleteResponse,
)
from .transcriptions import (
    TranscribeRequest,
    AssignTopicsToTranscriptionRequest,
    AddTranscriptionToCollectionRequest,
    TranscriptionChunkResponse,
    TranscriptionTopicResponse,
    TranscriptionCollectionResponse,
    AudioFileSummaryResponse,
    TranscriptionSummaryResponse,
    TranscriptionResponse,
    TranscriptionDetailResponse,
    TranscriptionListResponse,
    TranscriptionCreateResponse,
    TranscriptionDeleteResponse,
)

__all__ = [
    # Topics
    "TopicBase",
    "TopicCreate",
    "TopicUpdate",
    "TopicResponse",
    "TopicWithChildren",
    "TopicListResponse",
    # Collections
    "CollectionBase",
    "CollectionCreate",
    "CollectionUpdate",
    "CollectionResponse",
    "CollectionDetailResponse",
    "CollectionListResponse",
    # Job Topics
    "JobTopicResponse",
    "JobTopicListResponse",
    "AssignTopicsRequest",
    "UpdateTopicReviewRequest",
    # Job Collections
    "JobCollectionResponse",
    "JobCollectionListResponse",
    "AddToCollectionRequest",
    "UpdatePositionRequest",
    # Audio Files
    "AudioFileDownloadRequest",
    "AudioFileResponse",
    "AudioFileUploadResponse",
    "AudioFileListResponse",
    "AudioFileDetailResponse",
    "AudioFileDeleteResponse",
    # Transcriptions
    "TranscribeRequest",
    "AssignTopicsToTranscriptionRequest",
    "AddTranscriptionToCollectionRequest",
    "TranscriptionChunkResponse",
    "TranscriptionTopicResponse",
    "TranscriptionCollectionResponse",
    "AudioFileSummaryResponse",
    "TranscriptionSummaryResponse",
    "TranscriptionResponse",
    "TranscriptionDetailResponse",
    "TranscriptionListResponse",
    "TranscriptionCreateResponse",
    "TranscriptionDeleteResponse",
]
