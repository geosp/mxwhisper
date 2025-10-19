"""
SQLAlchemy models for MxWhisper
"""
from typing import Optional, List

from sqlalchemy import DateTime, String, Text, func, ForeignKey, Float, Integer, ARRAY
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
    authentik_token_identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Authentik token ID for revocation
    token_created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)  # When token was issued
    token_expires_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)  # When token expires
    token_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Human-readable token description

    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


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