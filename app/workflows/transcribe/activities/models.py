"""
Shared dataclasses for Temporal activities.

These models are used for activity inputs/outputs and must be serializable.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# Import ChunkMetadata from services to avoid circular imports
from ..services.ollama_service import ChunkMetadata


@dataclass
class TranscriptionSummary:
    """Result from transcribe_activity - lightweight summary to avoid event history bloat."""
    job_id: int
    success: bool
    segment_count: int
    character_count: int
    language: Optional[str]
    duration: Optional[float]


@dataclass
class ChunkingInput:
    """Input for chunk_with_ollama activity."""
    job_id: int
    transcript: Optional[str] = None  # Will be loaded from DB if not provided
    segments: Optional[List[Dict[str, Any]]] = None  # Will be loaded from DB if not provided


@dataclass
class ChunkingResult:
    """
    Result from chunk_with_ollama activity.

    TODO: Refactor to avoid passing chunks - store in DB instead.
    For now, keeping chunks to avoid breaking the workflow.
    """
    job_id: int
    success: bool
    chunk_count: int
    chunks: List[ChunkMetadata]  # TODO: Remove - causes event history bloat
    chunking_method: str  # "ollama", "sentence", "simple"


@dataclass
class EmbeddingInput:
    """
    Input for embed_chunks activity.

    Chunks are now loaded from database instead of being passed through event history.
    """
    job_id: int
    chunks: Optional[List[ChunkMetadata]] = None  # Deprecated - loaded from DB instead


@dataclass
class EmbeddingResult:
    """Result from embed_chunks activity."""
    job_id: int
    success: bool
    chunk_count: int
    embedding_count: int
