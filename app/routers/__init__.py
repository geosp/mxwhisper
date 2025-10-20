"""
API Routers for MxWhisper
"""
from .topics import router as topics_router
from .collections import router as collections_router
# from .job_topics import router as job_topics_router
# from .job_collections import router as job_collections_router
from .audio_files import router as audio_files_router
from .transcriptions import router as transcriptions_router

__all__ = [
    "topics_router",
    "collections_router",
    # "job_topics_router",
    # "job_collections_router",
    "audio_files_router",
    "transcriptions_router",
]
