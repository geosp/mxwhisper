"""
SQLAlchemy models for MxWhisper
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import DateTime, String, Text, func, ForeignKey, Float, Integer, ARRAY, Boolean, UniqueConstraint, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)  # admin, user, etc.
    description: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # Authentik user ID (sub claim)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    preferred_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), default=2)  # Foreign key to roles table
    role: Mapped[Role] = relationship("Role")  # Relationship to Role table

    # Authentik token metadata for service accounts
    token_created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)  # When token was issued
    token_expires_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)  # When token expires
    current_token_jti: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Current active token JTI for revocation
    token_revocation_counter: Mapped[int] = mapped_column(Integer, default=0)  # Counter for token revocation

    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    collections: Mapped[List["Collection"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"), nullable=True)  # Foreign key to users.id
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, processing, completed, failed
    transcript: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(384), nullable=True)  # Semantic embedding for search (384-dim) - deprecated, use chunks

    # New columns for job type polymorphism
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, default="transcription")  # 'download' | 'transcription'
    audio_file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("audio_files.id", ondelete="SET NULL"), nullable=True)  # For transcription jobs
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # For download jobs

    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship()
    audio_file: Mapped[Optional["AudioFile"]] = relationship(back_populates="jobs")


class Topic(Base):
    """
    Admin-managed hierarchical categorization system.
    Topics can have parent-child relationships for nested categories.
    """
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topics.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    parent: Mapped[Optional["Topic"]] = relationship("Topic", remote_side=[id], backref="children")


class Collection(Base):
    """
    User-managed groupings for organizing jobs.
    Can represent books, courses, series, albums, playlists, etc.
    """
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    collection_type: Mapped[Optional[str]] = mapped_column(String(50))  # 'book', 'course', 'series', 'album', etc.
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="collections")


class AudioFile(Base):
    """
    Stores all media files with ownership, checksums, and source information.
    Supports deduplication via SHA256 checksums.
    """
    __tablename__ = "audio_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # File storage
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # uploads/user_30/2025/10/checksum_file.mp3
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Bytes
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))  # audio/mpeg, audio/wav, etc.
    duration: Mapped[Optional[float]] = mapped_column(Float)  # Seconds

    # Deduplication
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 hash

    # Source tracking
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'upload' | 'download'
    source_url: Mapped[Optional[str]] = mapped_column(Text)  # Original URL if downloaded
    source_platform: Mapped[Optional[str]] = mapped_column(String(100))  # 'youtube', 'soundcloud', etc.

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship()
    transcriptions: Mapped[List["Transcription"]] = relationship(back_populates="audio_file", cascade="all, delete-orphan")
    jobs: Mapped[List["Job"]] = relationship(back_populates="audio_file")

    __table_args__ = (
        UniqueConstraint('user_id', 'checksum', name='uq_user_checksum'),
    )


class Transcription(Base):
    """
    Domain entity representing transcription results (decoupled from job orchestration).
    Each transcription belongs to an audio file and can have multiple chunks.
    """
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    audio_file_id: Mapped[int] = mapped_column(ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Transcription content
    transcript: Mapped[str] = mapped_column(Text, nullable=False)  # Full plaintext transcript
    from sqlalchemy.dialects.postgresql import JSONB
    segments: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Whisper segments as JSONB
    language: Mapped[Optional[str]] = mapped_column(String(10))  # Detected/specified language code

    # Model information
    model_name: Mapped[Optional[str]] = mapped_column(String(100))  # 'whisper-large-v3', etc.
    model_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Quality metrics
    avg_confidence: Mapped[Optional[float]] = mapped_column(Float)  # Average confidence across segments
    processing_time: Mapped[Optional[float]] = mapped_column(Float)  # Seconds taken to transcribe

    # Status tracking
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # 'pending' | 'processing' | 'completed' | 'failed'
    error_message: Mapped[Optional[str]] = mapped_column(Text)  # If status = 'failed'

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    audio_file: Mapped["AudioFile"] = relationship(back_populates="transcriptions")
    user: Mapped["User"] = relationship()
    chunks: Mapped[List["TranscriptionChunk"]] = relationship(back_populates="transcription", cascade="all, delete-orphan")
    transcription_topics: Mapped[List["TranscriptionTopic"]] = relationship(back_populates="transcription", cascade="all, delete-orphan")
    transcription_collections: Mapped[List["TranscriptionCollection"]] = relationship(back_populates="transcription", cascade="all, delete-orphan")


class TranscriptionChunk(Base):
    """
    Stores segments with embeddings for semantic search.
    Replaces JobChunk for new transcription workflow.
    """
    __tablename__ = "transcription_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)

    # Chunk content
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequential order within transcription
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Topic analysis (optional, for AI integration)
    topic_summary: Mapped[Optional[str]] = mapped_column(Text)  # AI-generated topic summary
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))  # Extracted keywords
    confidence: Mapped[Optional[float]] = mapped_column(Float)  # AI confidence score

    # Temporal alignment
    start_time: Mapped[Optional[float]] = mapped_column(Float)  # Seconds from start
    end_time: Mapped[Optional[float]] = mapped_column(Float)  # Seconds from start

    # Character positions (for text highlighting)
    start_char_pos: Mapped[Optional[int]] = mapped_column(Integer)
    end_char_pos: Mapped[Optional[int]] = mapped_column(Integer)

    # Semantic search
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(384))  # pgvector embedding

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    transcription: Mapped["Transcription"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint('transcription_id', 'chunk_index', name='uq_transcription_chunk'),
    )


class TranscriptionTopic(Base):
    """
    Junction table linking transcriptions to topics (replaces job_topics for new workflow).
    Supports both AI-assigned and user-assigned categorization.
    """
    __tablename__ = "transcription_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)

    # AI assignment tracking
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)  # AI confidence score (0.0-1.0)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text)  # Why AI assigned this topic

    # User assignment tracking
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))  # NULL if AI-assigned
    user_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)  # User confirmed/rejected

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    transcription: Mapped["Transcription"] = relationship(back_populates="transcription_topics")
    topic: Mapped["Topic"] = relationship()
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('transcription_id', 'topic_id', name='uq_transcription_topic'),
    )


class TranscriptionCollection(Base):
    """
    Junction table linking transcriptions to collections (replaces job_collections for new workflow).
    Allows transcriptions to be organized sequentially within collections.
    """
    __tablename__ = "transcription_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)

    position: Mapped[Optional[int]] = mapped_column(Integer)  # Order within collection
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))  # Who added to collection

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    transcription: Mapped["Transcription"] = relationship(back_populates="transcription_collections")
    collection: Mapped["Collection"] = relationship()
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('transcription_id', 'collection_id', name='uq_transcription_collection'),
    )