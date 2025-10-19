"""
SQLAlchemy models for MxWhisper
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import DateTime, String, Text, func, ForeignKey, Float, Integer, ARRAY, Boolean, UniqueConstraint
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
    segments: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)  # JSON string of segments with timestamps
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(384), nullable=True)  # Semantic embedding for search (384-dim) - deprecated, use chunks
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship()
    chunks: Mapped[List["JobChunk"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    job_topics: Mapped[List["JobTopic"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    job_collections: Mapped[List["JobCollection"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobChunk(Base):
    __tablename__ = "job_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    topic_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_char_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_char_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    job: Mapped["Job"] = relationship(back_populates="chunks")


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
    job_topics: Mapped[List["JobTopic"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


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
    job_collections: Mapped[List["JobCollection"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class JobTopic(Base):
    """
    Junction table linking jobs to topics with AI confidence tracking.
    Supports both AI-assigned and user-assigned categorization.
    """
    __tablename__ = "job_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)  # AI confidence score (0.0-1.0)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text)  # Why AI assigned this topic
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))  # NULL if AI-assigned
    user_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="job_topics")
    topic: Mapped["Topic"] = relationship(back_populates="job_topics")
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('job_id', 'topic_id', name='uq_job_topic'),
    )


class JobCollection(Base):
    """
    Junction table linking jobs to collections with position ordering.
    Allows jobs to be organized sequentially within collections (e.g., book chapters, course lessons).
    """
    __tablename__ = "job_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[Optional[int]] = mapped_column(Integer)  # Order within collection (for chapters, episodes)
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="job_collections")
    collection: Mapped["Collection"] = relationship(back_populates="job_collections")
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('job_id', 'collection_id', name='uq_job_collection'),
    )