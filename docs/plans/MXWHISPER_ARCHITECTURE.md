# MxWhisper System Architecture

## Overview
MxWhisper is an AI-powered audio transcription and knowledge management system that transforms audio content into searchable, categorized, and organized knowledge bases.

---

## System Purpose

### Primary Functions
1. **Audio Transcription** - Convert audio to text using Whisper AI
2. **Intelligent Chunking** - Break transcripts into semantic chunks
3. **Topic Categorization** - AI-powered topic assignment and classification
4. **Collection Management** - Organize content into series, books, courses
5. **Semantic Search** - Vector-based search across all content
6. **Knowledge Base API** - RESTful and MCP interfaces for content access

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MXWHISPER SYSTEM                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐      ┌──────────────┐      ┌────────────┐  │
│  │   Upload   │      │ Transcription│      │  Storage   │  │
│  │    API     │─────▶│   Pipeline   │─────▶│ & Search   │  │
│  └────────────┘      └──────────────┘      └────────────┘  │
│                                                              │
│  ┌────────────┐      ┌──────────────┐                       │
│  │ MCP Server │◀─────│  Knowledge   │                       │
│  │  (Tools)   │      │    Base      │                       │
│  └────────────┘      └──────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. API Layer (FastAPI)
**Purpose**: External interface for all operations

**Responsibilities**:
- User authentication and authorization
- File upload handling
- Job management (create, status, retrieve)
- Search endpoints (semantic + keyword)
- Topic and collection CRUD operations
- User management

**Key Endpoints**:
```
POST   /upload                    # Upload audio file
GET    /jobs/{id}                 # Get job status
GET    /jobs/{id}/transcript      # Get transcript
POST   /search                    # Search knowledge base
GET    /topics                    # List topics
GET    /collections               # List collections
POST   /jobs/{id}/topics          # Assign topics
POST   /jobs/{id}/collections     # Add to collection
```

**Technology**:
- FastAPI (Python)
- Pydantic for validation
- JWT authentication
- SQLAlchemy ORM

---

### 2. Transcription Pipeline (Temporal Workflows)
**Purpose**: Orchestrate multi-step audio processing

**Workflow Steps**:
```
1. Upload Audio
   ↓
2. Transcribe (Whisper AI)
   ↓
3. Create Chunks (semantic segmentation)
   ↓
4. Generate Embeddings (vector representations)
   ↓
5. AI Categorization (topic assignment)
   ↓
6. Complete (notify user)
```

**Activities**:
- `transcribe_audio_activity` - Whisper transcription
- `create_chunks_activity` - Semantic chunking with topic summaries
- `generate_embeddings_activity` - Vector embeddings
- `categorize_job_activity` - AI topic/collection classification
- `store_results_activity` - Persist to database

**Technology**:
- Temporal workflows (Python SDK)
- Whisper AI (OpenAI or local)
- Sentence transformers for embeddings
- LLM for categorization (Claude/GPT)

**Why Temporal**:
- Durable execution (survives crashes)
- Retry logic built-in
- Async task orchestration
- Workflow versioning
- Observable execution history

---

### 3. Data Layer (PostgreSQL + Redis)

#### PostgreSQL Schema

**Core Tables**:
```sql
users               # User accounts
jobs                # Transcription jobs
transcripts         # Full transcripts
chunks              # Semantic chunks with embeddings
topics              # Admin-managed categories (hierarchical)
collections         # User-managed groupings (series, books)
job_topics          # Many-to-many: jobs ↔ topics
job_collections     # Many-to-many: jobs ↔ collections
```

**Key Relationships**:
- User → Jobs (one-to-many)
- Job → Transcript (one-to-one)
- Transcript → Chunks (one-to-many)
- Job → Topics (many-to-many via job_topics)
- Job → Collections (many-to-many via job_collections)
- Topic → Topic (self-referencing for hierarchy)

**Indexes**:
- Vector index on `chunks.embedding` (pgvector)
- Full-text search on `chunks.text`
- Job status, user_id, created_at
- Topic and collection foreign keys

#### Redis Cache
**Purpose**: Performance optimization

**Cached Data**:
- User sessions (JWT blacklist)
- Rate limiting counters
- Job status updates (before DB write)
- Topic hierarchy (rarely changes)
- Search results (short TTL)

---

### 4. AI Services

#### Topic Classifier
**Purpose**: Automatically assign topics to transcripts

**Input**:
- Chunk topic summaries (already generated during chunking)
- Available topics from database

**Process**:
```
1. Aggregate chunk summaries
2. Build topic hierarchy context
3. Call LLM with classification prompt
4. Parse structured response (topic_id, confidence, reasoning)
5. Store in job_topics table
```

**Output**:
```json
{
  "assignments": [
    {
      "topic_id": 2,
      "topic_name": "Bible Study",
      "confidence": 0.92,
      "reasoning": "Content discusses biblical teachings"
    }
  ]
}
```

**Confidence Thresholds**:
- `> 0.8` - Auto-assign
- `0.6 - 0.8` - Flag for review
- `< 0.6` - Skip assignment

#### Collection Classifier
**Purpose**: Suggest collection membership or new collections

**Strategies**:
1. **Pattern Matching**: Detect series patterns in filenames
   - "Romans Chapter 3" → Series: "Romans", Episode: 3
   - "Sermon EP042" → Series: "Sermon", Episode: 42

2. **Content Similarity**: Compare with existing collections
   - Use embeddings to find similar jobs
   - Suggest adding to existing collection

3. **New Collection Detection**: Identify series potential
   - Multiple jobs with similar titles
   - Sequential numbering patterns

---

### 5. MCP Server (Knowledge Base Interface)
**Purpose**: AI-native interface for knowledge base interaction

**Mode**: HTTP (for n8n and external integrations)

**MCP Tools** (auto-discovered from `features/` directory):

```
search_knowledge_base()      # Semantic search
list_topics()                # Browse topics
get_jobs_by_topic()          # Filter by topic
list_collections()           # Browse collections
get_collection()             # Get collection with jobs
create_collection()          # Create new collection
add_job_to_collection()      # Add job to collection
get_job()                    # Get job details
get_transcript()             # Read full transcript
upload_audio()               # Upload new audio
```

**Integration Points**:
- Claude Desktop (stdio mode, future)
- n8n workflows (HTTP mode)
- Other AI agents (HTTP mode)
- Custom applications (REST API)

**Architecture Pattern**: mcp-weather core with automatic feature discovery

---

## Data Flow Diagrams

### Upload & Transcription Flow

```
User
  │
  ├─ POST /upload (audio file, optional: topics, collection)
  │
  ▼
API Server
  │
  ├─ Validate file
  ├─ Create Job record (status: pending)
  ├─ Save file to storage
  ├─ Start Temporal workflow
  │
  ▼
Temporal Workflow
  │
  ├─ Activity: Transcribe Audio (Whisper)
  │   └─ Output: Full transcript text
  │
  ├─ Activity: Create Chunks
  │   ├─ Semantic segmentation
  │   └─ Generate topic summary per chunk (LLM)
  │
  ├─ Activity: Generate Embeddings
  │   └─ Vector representations for each chunk
  │
  ├─ Activity: AI Categorization (if no manual topics)
  │   ├─ TopicClassifier: Assign topics
  │   └─ CollectionClassifier: Suggest collections
  │
  ├─ Activity: Store Results
  │   ├─ Save transcript to DB
  │   ├─ Save chunks with embeddings
  │   └─ Save topic assignments
  │
  └─ Update Job (status: completed)
```

### Search Flow

```
User/Agent
  │
  ├─ POST /search or search_knowledge_base() via MCP
  │   ├─ query: "Romans 3 faith"
  │   ├─ topic_ids: [2, 5] (optional)
  │   └─ collection_ids: [1] (optional)
  │
  ▼
API Server / MCP Server
  │
  ├─ Generate query embedding
  │
  ├─ Vector search in chunks table
  │   ├─ Filter by topic_ids (join job_topics)
  │   ├─ Filter by collection_ids (join job_collections)
  │   └─ ORDER BY embedding <-> query_embedding
  │
  ├─ Retrieve matching chunks
  │
  ├─ Group by job_id
  │
  └─ Return results with context
      ├─ job_id, title
      ├─ relevant chunks
      ├─ topics
      └─ collections
```

### Topic Assignment Flow

```
Temporal Workflow (Categorization Activity)
  │
  ├─ Load job and chunks from DB
  │
  ├─ Extract chunk topic summaries
  │
  ├─ Load available topics (hierarchical)
  │
  ▼
TopicClassifier
  │
  ├─ Aggregate summaries into coherent overview
  │
  ├─ Build topic hierarchy context for LLM
  │
  ├─ Call LLM with classification prompt
  │   ├─ Input: content summary + topic list
  │   └─ Output: JSON with topic assignments
  │
  ├─ Parse LLM response
  │
  └─ Return TopicAssignment objects
      ├─ topic_id
      ├─ confidence
      └─ reasoning
  │
  ▼
Temporal Workflow
  │
  ├─ For each assignment:
  │   └─ Create job_topics record
  │       ├─ ai_confidence = 0.92
  │       ├─ ai_reasoning = "..."
  │       ├─ assigned_by = NULL (AI)
  │       └─ user_reviewed = false
  │
  └─ Complete workflow
```

---

## Integration Points

### 1. Existing Infrastructure (Kubernetes)
- **PostgreSQL**: Shared database server (separate database: `mxwhisper`)
- **Redis**: Shared cache (separate namespace: `mxwhisper:*`)
- **Temporal**: Shared Temporal server (separate namespace: `mxwhisper`)

### 2. External Services
- **LLM Provider**: OpenAI/Anthropic for categorization
- **Whisper API**: Transcription (local or OpenAI)
- **Embedding Model**: Sentence transformers or OpenAI

### 3. Consumers
- **n8n**: Workflows consume MCP server (HTTP mode)
- **MxPodcaster**: Content creation system (future)
- **Claude Desktop**: Direct MCP integration (future)

---

## Scalability Considerations

### Horizontal Scaling
- **API Server**: Stateless, scale to N replicas
- **Temporal Workers**: Scale based on queue depth
- **MCP Server**: Stateless, scale to N replicas

### Vertical Scaling
- **Transcription**: CPU/GPU intensive, large workers
- **Embeddings**: CPU intensive, medium workers
- **Categorization**: LLM API calls, lightweight workers

### Storage Scaling
- **Audio Files**: Object storage (S3-compatible) or large PVCs
- **Database**: PostgreSQL connection pooling, read replicas
- **Vectors**: pgvector with HNSW index for large-scale search

---

## Security Architecture

### Authentication
- **JWT Tokens**: For API access
- **API Keys**: For MCP server access
- **Service Accounts**: For n8n integration

### Authorization
- **User-owned Resources**: Jobs, collections
- **Admin-only**: Topic management
- **Public**: Search (within user's content)

### Data Protection
- **At Rest**: Encrypted storage (Ceph encryption)
- **In Transit**: TLS for all HTTP traffic
- **Secrets**: Kubernetes secrets for credentials

---

## Performance Optimization

### Caching Strategy
```
Redis Cache:
├─ User sessions (TTL: 24h)
├─ Topic hierarchy (TTL: 1h, invalidate on change)
├─ Search results (TTL: 5min)
└─ Job status (TTL: 1min, write-through)
```

### Database Optimization
```
Indexes:
├─ chunks.embedding (HNSW vector index)
├─ chunks.text (GIN full-text index)
├─ jobs(user_id, created_at)
├─ job_topics(job_id, topic_id)
└─ job_collections(collection_id, position)

Connection Pooling:
├─ Min: 5 connections
├─ Max: 20 connections
└─ Overflow: 10 connections
```

### Async Processing
```
Temporal Workflows:
├─ Transcription: 5-30 min (async)
├─ Chunking: 1-5 min (async)
├─ Embeddings: 2-10 min (async)
└─ Categorization: 10-60 sec (async)

Total: User gets immediate job ID, processing happens async
```

---

## Observability

### Metrics to Track
- API request rate, latency, errors
- Transcription job throughput, success rate
- Worker queue depth, processing time
- Database query performance
- Cache hit rate
- Storage usage

### Logging Strategy
```
Structured Logging (JSON):
├─ API requests (request_id, user_id, endpoint, duration)
├─ Workflow events (workflow_id, activity, status)
├─ Errors (stack trace, context)
└─ Audit logs (user actions, topic changes)
```

### Health Checks
```
/health endpoint:
├─ Database connectivity
├─ Redis connectivity
├─ Temporal connectivity
├─ Storage accessibility
└─ LLM API availability
```

---

## Extension Points

### Future Enhancements
1. **Multi-language Support**: Detect language, transcribe accordingly
2. **Speaker Diarization**: Identify different speakers
3. **Custom Vocabularies**: Domain-specific terminology
4. **Live Transcription**: Real-time audio streaming
5. **Export Formats**: PDF, DOCX, SRT subtitles
6. **Collaborative Features**: Shared collections, annotations
7. **Analytics Dashboard**: Usage statistics, trends

### Plugin Architecture
```
Future: Plugin system for custom processors
├─ Pre-transcription: Audio normalization, noise reduction
├─ Post-transcription: Custom chunking strategies
├─ Custom categorizers: Domain-specific topic models
└─ Export handlers: Custom output formats
```

---

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI | REST API server |
| Workflows | Temporal | Async orchestration |
| Database | PostgreSQL + pgvector | Data storage + vector search |
| Cache | Redis | Session & performance cache |
| AI Models | Whisper, Sentence Transformers, Claude/GPT | Transcription, embeddings, categorization |
| MCP | FastMCP + mcp-weather core | Knowledge base interface |
| Storage | Ceph RBD (K8s PVCs) | File storage |
| Deployment | Kubernetes (RKE2) | Container orchestration |
| IaC | Ansible | Deployment automation |

---

## Design Principles

### 1. Separation of Concerns
- API layer handles HTTP, not business logic
- Temporal workflows orchestrate, not execute
- Activities are pure functions (no side effects)

### 2. Fail-Safe Design
- Temporal ensures durable execution
- Jobs can be retried without data loss
- Graceful degradation (categorization failure ≠ transcription failure)

### 3. Extensibility
- MCP feature discovery (add features without changing core)
- Plugin architecture (future)
- API versioning ready

### 4. Performance First
- Async processing for long tasks
- Caching at multiple levels
- Vector search for semantic queries
- Horizontal scaling ready

### 5. AI-Native
- MCP as primary interface
- Chunk-based AI processing
- Confidence scoring for transparency
- Human-in-the-loop for corrections

---

## Related Documents

- [Phase 1: Database & Models](collections_and_topics/PHASE_1_DATABASE_AND_MODELS.md)
- [Phase 2: API Endpoints](collections_and_topics/PHASE_2_API_ENDPOINTS.md)
- [Phase 3: AI Integration](collections_and_topics/PHASE_3_AI_INTEGRATION.md)
- [Phase 4: MCP Server](collections_and_topics/PHASE_4_MCP_SERVER.md)
- [MxPodcaster Architecture](MXPODCASTER_ARCHITECTURE.md) (next)
- [Ecosystem Integration](ECOSYSTEM_ARCHITECTURE.md) (next)

---

**Document Status**: Architecture Planning
**Last Updated**: 2025-10-19
**Version**: 1.0
