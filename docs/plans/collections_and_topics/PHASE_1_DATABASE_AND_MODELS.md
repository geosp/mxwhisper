# Phase 1: Database & Models

## Overview
Establish the foundational data structures for topic categorization and collection management in MxWhisper.

## Goals
- Create all necessary database tables
- Implement SQLAlchemy models
- Add proper indexes for performance
- Create database migration scripts
- Seed initial topic hierarchy

---

## 1.1 Database Schema

### Topics Table (Admin-Managed Categories)
```sql
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INTEGER REFERENCES topics(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for hierarchy queries
CREATE INDEX idx_topics_parent_id ON topics(parent_id);
```

### Collections Table (User-Managed Groupings)
```sql
CREATE TABLE collections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    collection_type VARCHAR(50), -- 'book', 'course', 'series', 'album', etc.
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE CASCADE, -- String ID from Authentik
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for user-based queries
CREATE INDEX idx_collections_user_id ON collections(user_id);
CREATE INDEX idx_collections_type ON collections(collection_type);
```

### Job-Topic Relationships
```sql
CREATE TABLE job_topics (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    ai_confidence FLOAT,         -- AI confidence score (0.0-1.0)
    ai_reasoning TEXT,           -- Why AI assigned this topic
    assigned_by VARCHAR(255) REFERENCES users(id), -- NULL if AI-assigned (String ID from Authentik)
    user_reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_id, topic_id)
);

-- Indexes for filtering and searching
CREATE INDEX idx_job_topics_job_id ON job_topics(job_id);
CREATE INDEX idx_job_topics_topic_id ON job_topics(topic_id);
CREATE INDEX idx_job_topics_confidence ON job_topics(ai_confidence);
CREATE INDEX idx_job_topics_reviewed ON job_topics(user_reviewed);
```

### Job-Collection Relationships
```sql
CREATE TABLE job_collections (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    position INTEGER,            -- Order within collection (for chapters, episodes)
    assigned_by VARCHAR(255) REFERENCES users(id), -- String ID from Authentik
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_id, collection_id)
);

-- Indexes for filtering and ordering
CREATE INDEX idx_job_collections_job_id ON job_collections(job_id);
CREATE INDEX idx_job_collections_collection_id ON job_collections(collection_id);
CREATE INDEX idx_job_collections_position ON job_collections(collection_id, position);
```

---

## 1.2 SQLAlchemy Models

### Topic Model
```python
class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topics.id"))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    # Relationships
    parent: Mapped[Optional["Topic"]] = relationship("Topic", remote_side=[id], backref="children")
    job_topics: Mapped[List["JobTopic"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
```

### Collection Model
```python
class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    collection_type: Mapped[Optional[str]] = mapped_column(String(50))
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # String ID from Authentik
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="collections")
    job_collections: Mapped[List["JobCollection"]] = relationship(back_populates="collection", cascade="all, delete-orphan")
```

### JobTopic Model
```python
class JobTopic(Base):
    __tablename__ = "job_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)  # AI confidence score (0.0-1.0)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))  # String ID from Authentik
    user_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="job_topics")
    topic: Mapped["Topic"] = relationship(back_populates="job_topics")
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('job_id', 'topic_id', name='uq_job_topic'),
    )
```

### JobCollection Model
```python
class JobCollection(Base):
    __tablename__ = "job_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[Optional[int]] = mapped_column(Integer)
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey("users.id"))  # String ID from Authentik
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="job_collections")
    collection: Mapped["Collection"] = relationship(back_populates="job_collections")
    assigner: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        UniqueConstraint('job_id', 'collection_id', name='uq_job_collection'),
    )
```

### Updates to Existing Models

#### User Model
```python
# Add to User model
collections: Mapped[List["Collection"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

#### Job Model
```python
# Add to Job model
job_topics: Mapped[List["JobTopic"]] = relationship(back_populates="job", cascade="all, delete-orphan")
job_collections: Mapped[List["JobCollection"]] = relationship(back_populates="job", cascade="all, delete-orphan")
```

---

## 1.3 Database Migration

### Alembic Migration Script Structure
```python
"""Add topic categorization and collection management

Revision ID: xxxx
Revises: previous_revision
Create Date: 2025-10-18
"""

def upgrade():
    # Create topics table
    op.create_table('topics', ...)
    op.create_index('idx_topics_parent_id', 'topics', ['parent_id'])

    # Create collections table
    op.create_table('collections', ...)
    op.create_index('idx_collections_user_id', 'collections', ['user_id'])
    op.create_index('idx_collections_type', 'collections', ['collection_type'])

    # Create job_topics junction table
    op.create_table('job_topics', ...)
    op.create_index('idx_job_topics_job_id', 'job_topics', ['job_id'])
    op.create_index('idx_job_topics_topic_id', 'job_topics', ['topic_id'])
    op.create_index('idx_job_topics_confidence', 'job_topics', ['ai_confidence'])
    op.create_index('idx_job_topics_reviewed', 'job_topics', ['user_reviewed'])

    # Create job_collections junction table
    op.create_table('job_collections', ...)
    op.create_index('idx_job_collections_job_id', 'job_collections', ['job_id'])
    op.create_index('idx_job_collections_collection_id', 'job_collections', ['collection_id'])
    op.create_index('idx_job_collections_position', 'job_collections', ['collection_id', 'position'])

def downgrade():
    # Drop tables in reverse order
    op.drop_table('job_collections')
    op.drop_table('job_topics')
    op.drop_table('collections')
    op.drop_table('topics')
```

---

## 1.4 Initial Topic Seed Data

### Sample Topic Hierarchy
```python
# Migration data seeding or separate script
initial_topics = [
    # Root categories
    {"name": "Religious", "description": "Religious and spiritual content"},
    {"name": "Educational", "description": "Educational and instructional content"},
    {"name": "Entertainment", "description": "Entertainment and media content"},
    {"name": "Professional", "description": "Professional and business content"},

    # Religious subcategories
    {"name": "Bible Study", "description": "Bible studies and scriptural analysis", "parent": "Religious"},
    {"name": "Sermons", "description": "Sermons and preaching", "parent": "Religious"},
    {"name": "Prayer", "description": "Prayer and devotional content", "parent": "Religious"},
    {"name": "Worship", "description": "Worship music and services", "parent": "Religious"},

    # Educational subcategories
    {"name": "Courses", "description": "Educational courses and lectures", "parent": "Educational"},
    {"name": "Tutorials", "description": "How-to guides and tutorials", "parent": "Educational"},
    {"name": "Conferences", "description": "Conference talks and presentations", "parent": "Educational"},

    # Entertainment subcategories
    {"name": "Podcasts", "description": "Podcast episodes", "parent": "Entertainment"},
    {"name": "Audiobooks", "description": "Audiobook recordings", "parent": "Entertainment"},
    {"name": "Interviews", "description": "Interviews and conversations", "parent": "Entertainment"},

    # Professional subcategories
    {"name": "Meetings", "description": "Business meetings and discussions", "parent": "Professional"},
    {"name": "Presentations", "description": "Professional presentations", "parent": "Professional"},
]
```

---

## 1.5 Validation & Testing

### Database Constraints Testing
- Verify UNIQUE constraints work (job_id, topic_id) and (job_id, collection_id)
- Test CASCADE deletes (deleting job removes associations)
- Test foreign key constraints
- Verify indexes improve query performance

### Model Testing
- Test Topic hierarchy (parent-child relationships)
- Test Collection ownership (user_id foreign key)
- Test JobTopic creation with confidence scores
- Test JobCollection ordering (position field)

### Migration Testing
- Run upgrade migration
- Verify all tables and indexes created
- Insert seed data
- Run downgrade migration
- Verify clean rollback

---

## Deliverables

- [ ] SQL schema files for all tables
- [ ] SQLAlchemy model classes
- [ ] Alembic migration scripts
- [ ] Topic seed data script
- [ ] Unit tests for models
- [ ] Migration testing verification
- [ ] Database documentation

---

## Success Criteria

- All tables created with proper foreign keys and constraints
- Indexes improve query performance (verified with EXPLAIN)
- Models pass SQLAlchemy relationship tests
- Migration can upgrade and downgrade cleanly
- Seed data populates initial topic hierarchy
- No breaking changes to existing jobs/users tables

---

**Estimated Effort**: 2-3 days
**Dependencies**: None (pure database/model work)
**Next Phase**: Phase 2 - API Endpoints
