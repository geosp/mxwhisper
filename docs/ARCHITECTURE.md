# MxWhisper Architecture Documentation

## Table of Contents

- [Overview](#overview)
- [Architectural Patterns](#architectural-patterns)
- [Component Design](#component-design)
- [Data Flow](#data-flow)
- [Scalability Considerations](#scalability-considerations)
- [Error Handling & Resilience](#error-handling--resilience)
- [Performance Optimizations](#performance-optimizations)
- [Security Architecture](#security-architecture)

## Overview

MxWhisper is built on a **layered service-oriented architecture** with clear separation of concerns. The system is designed for scalability, reliability, and maintainability using industry-standard patterns and practices.

### Core Design Principles

1. **Separation of Concerns**: Each layer has a distinct responsibility
2. **Async-First**: Full async/await throughout the stack for high concurrency
3. **Event-Driven**: Temporal workflows for reliable async processing
4. **Stateless API**: API servers can scale horizontally
5. **Database as Source of Truth**: PostgreSQL stores all persistent state
6. **Idempotent Operations**: Retry-safe activities and workflows

## Architectural Patterns

### 1. Layered Architecture

```mermaid
graph TD
    subgraph "Presentation Layer"
        A[FastAPI Endpoints]
        B[WebSocket Handlers]
    end

    subgraph "Service Layer"
        C[Job Service]
        D[User Service]
        E[Embedding Service]
        F[WebSocket Manager]
    end

    subgraph "Domain Layer"
        G[Business Logic]
        H[Validation Rules]
    end

    subgraph "Workflow Orchestration Layer"
        I[Temporal Workflows]
        J[Activities]
    end

    subgraph "Data Access Layer"
        K[SQLAlchemy Models]
        L[Database Sessions]
    end

    subgraph "Infrastructure Layer"
        M[(PostgreSQL + pgvector)]
        N[AI/ML Services]
        O[Authentik]
    end

    A --> C
    A --> D
    B --> F
    C --> G
    C --> I
    D --> G
    E --> N
    G --> K
    I --> J
    J --> N
    J --> K
    K --> L
    L --> M
    A --> O
```

**Benefits:**
- Clear boundaries between layers
- Easy to test each layer independently
- Changes in one layer don't affect others
- Supports horizontal scaling

### 2. Service-Oriented Pattern

Each service has a single, well-defined responsibility:

| Service | Responsibility | Dependencies |
|---------|---------------|--------------|
| **JobService** | Job lifecycle management, workflow triggering | Temporal, Database |
| **UserService** | User management, role verification | Database, Authentik |
| **EmbeddingService** | Vector embedding generation | SentenceTransformers |
| **WebSocketManager** | Real-time client notifications | In-memory connection registry |

**Key Characteristics:**
- Services are stateless
- Services communicate through well-defined interfaces
- Services can be deployed independently (if needed)

### 3. Activity-Based Workflow Pattern (Temporal)

Workflows orchestrate long-running, multi-step processes:

```mermaid
stateDiagram-v2
    [*] --> Pending: Job Created
    Pending --> Processing: Workflow Started

    state Processing {
        [*] --> Transcribing
        Transcribing --> Chunking: Transcript Ready
        Chunking --> Embedding: Chunks Ready
        Embedding --> [*]: Complete
    }

    Processing --> Completed: Success
    Processing --> Failed: Error

    Completed --> [*]
    Failed --> [*]
```

**Temporal Benefits:**
- **Durability**: Workflows survive process crashes
- **Visibility**: Full execution history and monitoring
- **Retries**: Automatic retry with exponential backoff
- **Timeouts**: Configurable timeouts for each activity
- **Heartbeats**: Long-running activities send progress updates

### 4. Repository Pattern (Implicit)

SQLAlchemy models act as repositories for data access:

```python
# Example: Job repository operations
async def create_job(db: AsyncSession, filename: str, content: bytes) -> Job:
    job = Job(filename=filename, file_path=path, status="pending")
    db.add(job)
    await db.commit()
    return job
```

**Benefits:**
- Abstraction over database operations
- Testable with mock databases
- Consistent data access patterns

## Component Design

### API Layer ([main.py](../main.py))

**Responsibilities:**
- HTTP request/response handling
- Request validation (Pydantic models)
- Authentication/authorization
- WebSocket connection management
- CORS configuration

**Design Decisions:**
- FastAPI for automatic OpenAPI documentation
- Dependency injection for database sessions and auth
- Async endpoints for high concurrency
- WebSocket for real-time updates (no polling needed)

**Key Endpoints:**
```python
POST   /upload              # Upload audio file
GET    /jobs/{id}           # Get job status
GET    /jobs/{id}/download  # Download transcript
POST   /search              # Semantic search
WS     /ws/jobs/{id}        # Real-time updates
GET    /admin/jobs          # Admin: all jobs
GET    /admin/users         # Admin: all users
```

### Service Layer ([app/services/](../app/services/))

#### JobService ([job_service.py](../app/services/job_service.py))

**Responsibilities:**
- Create and manage transcription jobs
- Trigger Temporal workflows
- Query job status and results

**Key Operations:**
```python
create_job()        # Create new job record
trigger_workflow()  # Start Temporal workflow
get_job()          # Fetch job by ID
get_user_jobs()    # Get user's jobs
get_all_jobs()     # Admin: get all jobs
```

#### UserService ([user_service.py](../app/services/user_service.py))

**Responsibilities:**
- User registration and management
- Role assignment and verification
- Integration with Authentik

**Key Operations:**
```python
initialize_roles()      # Setup default roles
get_or_create_user()   # Create user from JWT
is_admin()             # Check admin privileges
```

#### EmbeddingService ([embedding_service.py](../app/services/embedding_service.py))

**Responsibilities:**
- Generate semantic embeddings from text
- Batch processing for efficiency
- Vector normalization

**Key Operations:**
```python
generate_embedding(text)          # Single embedding
generate_embeddings_batch(texts)  # Batch embeddings
```

**Model:**
- `all-MiniLM-L6-v2`: 384-dimensional embeddings
- Runs on CPU (no GPU required)
- ~80MB model size
- Fast inference (<10ms per sentence)

### Workflow Layer ([app/workflows/transcribe/](../app/workflows/transcribe/))

#### TranscribeWorkflow ([workflow.py](../app/workflows/transcribe/workflow.py))

**Orchestration Flow:**
1. Execute `transcribe_activity` → Get transcript + segments
2. Execute `chunk_with_ollama_activity` → Create semantic chunks
3. Execute `embed_chunks_activity` → Generate embeddings

**Temporal Configuration:**
```python
start_to_close_timeout = timedelta(hours=1)  # Transcription
start_to_close_timeout = timedelta(minutes=30)  # Chunking
start_to_close_timeout = timedelta(minutes=10)  # Embedding
retry_policy = RetryPolicy(maximum_attempts=3)
```

#### Activities

**1. Transcribe Activity** ([transcribe.py](../app/workflows/transcribe/activities/transcribe.py))
- Loads audio file from uploads directory
- Calls WhisperService for transcription
- Stores transcript and timestamped segments
- Returns lightweight summary (avoids event history bloat)

**2. Chunk Activity** ([chunk.py](../app/workflows/transcribe/activities/chunk.py))
- Uses OllamaService (vLLM/Ollama) for topic analysis
- Identifies semantic boundaries in transcript
- Creates chunks with topic summaries and keywords
- Maps chunks to Whisper segment timestamps
- **Fallback strategy**: Sentence-based chunking if LLM fails

**3. Embed Activity** ([embed.py](../app/workflows/transcribe/activities/embed.py))
- Loads chunks from database (avoids Temporal event bloat)
- Batch generates embeddings for all chunks
- Updates JobChunk records with vectors
- Marks job as completed

### Data Layer ([app/data/](../app/data/))

#### Models ([models.py](../app/data/models.py))

**Design Patterns:**
- Declarative base with typed mappings
- Relationships for ORM navigation
- Cascade deletes for cleanup
- Timestamps for audit trails

**Vector Storage:**
```python
class JobChunk:
    embedding: Mapped[Optional[Vector]] = mapped_column(
        Vector(384),  # pgvector type
        nullable=True
    )
```

**Indexes:**
```sql
-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX job_chunks_embedding_idx
ON job_chunks
USING hnsw (embedding vector_cosine_ops);
```

### AI/ML Services

#### WhisperService ([whisper_service.py](../app/workflows/transcribe/services/whisper_service.py))

**Capabilities:**
- Multi-language transcription
- Automatic language detection
- Timestamped segments
- Word-level timestamps (optional)

**Model Sizes:**
- `tiny` (39M): Fastest, lowest accuracy
- `base` (74M): Default, balanced
- `small` (244M): Better accuracy
- `medium` (769M): High accuracy
- `large` (1550M): Best accuracy

**GPU Acceleration:**
- Uses CUDA if available
- Falls back to CPU if no GPU
- Model preloaded during Docker build

#### OllamaService ([ollama_service.py](../app/workflows/transcribe/services/ollama_service.py))

**Capabilities:**
- Topic boundary detection
- Semantic chunk creation
- Topic summarization
- Keyword extraction

**LLM Configuration:**
```python
model = "hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4"
base_url = "http://vllm-server:8000"  # vLLM or Ollama
timeout = 300s
max_retries = 3
```

**Prompting Strategy:**
```
Analyze this transcript and identify distinct topics.
For each topic segment, provide:
1. Start/end character positions
2. Topic summary (1-2 sentences)
3. Keywords (3-5)
4. Confidence score
```

## Data Flow

### Transcription Pipeline

```mermaid
flowchart LR
    subgraph Client
        A[User]
    end

    subgraph API
        B[POST /upload]
        C[WebSocket]
    end

    subgraph Database
        D[(Jobs Table)]
        E[(JobChunks Table)]
    end

    subgraph Temporal
        F[Workflow]
        G[Activities]
    end

    subgraph AI Services
        H[Whisper]
        I[vLLM]
        J[SentenceTransformers]
    end

    A -->|Audio File| B
    B -->|Create Job| D
    B -->|Trigger| F
    B -->|Job ID| A

    F --> G
    G -->|Transcribe| H
    H -->|Text + Segments| D

    G -->|Analyze Topics| I
    I -->|Chunks + Metadata| E

    G -->|Generate Embeddings| J
    J -->|Vectors| E

    D -->|Status Updates| C
    E -->|Status Updates| C
    C -->|Real-time| A

    style D fill:#50C878
    style E fill:#50C878
    style H fill:#4A90E2
    style I fill:#F5A623
    style J fill:#9B59B6
```

### Semantic Search Flow

```mermaid
flowchart LR
    subgraph Client
        A[User]
    end

    subgraph API
        B[POST /search]
    end

    subgraph Services
        C[EmbeddingService]
    end

    subgraph AI
        D[SentenceTransformers]
    end

    subgraph Database
        E[(pgvector)]
        F[HNSW Index]
    end

    A -->|Query: 'biblical teachings'| B
    B --> C
    C -->|Generate Query Embedding| D
    D -->|384-dim vector| C
    C -->|Vector Search| E
    E -->|Use Index| F
    F -->|Top K Results| E
    E -->|Ranked Chunks| B
    B -->|Search Results| A

    style E fill:#50C878
    style F fill:#50C878
    style D fill:#9B59B6
```

## Scalability Considerations

### Horizontal Scaling

**API Servers:**
- Stateless design allows unlimited horizontal scaling
- Load balancer distributes requests
- Shared PostgreSQL database
- WebSocket connections: sticky sessions recommended

**Temporal Workers:**
- Scale workers based on queue depth
- Each worker processes activities in parallel
- Workers can run on separate machines
- GPU-enabled workers for Whisper tasks

**Database:**
- PostgreSQL with read replicas
- pgvector HNSW index for O(log n) search
- Connection pooling via SQLAlchemy
- Async driver (asyncpg) for high concurrency

### Performance Optimization Strategies

1. **Batch Processing**
   ```python
   # Generate embeddings in batch (10x faster)
   embeddings = generate_embeddings_batch(texts)
   ```

2. **Async Operations**
   ```python
   # All I/O is async
   async with AsyncSession() as session:
       job = await session.get(Job, job_id)
   ```

3. **Model Preloading**
   ```dockerfile
   # Whisper model loaded during Docker build
   RUN python -c "import whisper; whisper.load_model('medium')"
   ```

4. **Vector Index Optimization**
   ```sql
   -- HNSW index parameters tuned for accuracy/speed tradeoff
   CREATE INDEX USING hnsw (embedding vector_cosine_ops)
   WITH (m = 16, ef_construction = 64);
   ```

5. **Database Query Optimization**
   ```python
   # Efficient vector search with user scoping
   SELECT * FROM job_chunks
   WHERE job_id IN (SELECT id FROM jobs WHERE user_id = ?)
   ORDER BY embedding <=> ? LIMIT 10
   ```

### Resource Management

**Memory:**
- Whisper models loaded once per worker
- SentenceTransformers model cached
- Database connection pooling
- Temporal event history kept minimal

**Storage:**
- Audio files stored temporarily, deleted after processing
- Transcripts stored in PostgreSQL
- No file-based caching needed

**GPU:**
- Whisper uses GPU if available
- vLLM uses GPU for LLM inference
- SentenceTransformers runs on CPU

## Error Handling & Resilience

### Retry Strategies

**Temporal Activities:**
```python
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=60),
    backoff_coefficient=2.0,
    maximum_attempts=3
)
```

**HTTP Requests (Ollama/vLLM):**
```python
timeout = httpx.Timeout(
    connect=60,
    read=240,
    write=60,
    pool=60
)
max_retries = 3
```

### Failure Handling

**1. Whisper Transcription Fails:**
- Workflow marks job as "failed"
- Error logged with context
- User notified via WebSocket
- Job can be retried manually

**2. LLM Service Unavailable:**
- Automatic fallback to sentence-based chunking
- Warning logged
- Processing continues with degraded chunking

**3. Database Connection Lost:**
- SQLAlchemy automatic reconnection
- Temporal automatically retries activity
- Transaction rollback on failure

**4. Worker Crashes:**
- Temporal reschedules workflow on another worker
- Heartbeats detect stuck activities
- Activities are idempotent (safe to retry)

### Heartbeat Mechanism

```python
# Long-running activities send heartbeats
activity.heartbeat("Processing segment 10/100")

# Temporal detects failures
heartbeat_timeout = timedelta(minutes=5)
```

**Benefits:**
- Detect stuck workers
- Show progress to users
- Timeout protection

## Performance Optimizations

### 1. Avoid Temporal Event History Bloat

**Problem:** Temporal stores all activity inputs/outputs in event history.

**Solution:**
- Pass only job IDs to activities
- Activities load data from database
- Return minimal summaries

```python
# BAD: Passing large transcript through Temporal
chunking_result = await workflow.execute_activity(
    "chunk_activity",
    {"transcript": large_text, "segments": segments}  # ❌ Event bloat
)

# GOOD: Pass only job ID
chunking_result = await workflow.execute_activity(
    "chunk_activity",
    {"job_id": job_id}  # ✅ Activity loads from DB
)
```

### 2. Batch Embedding Generation

```python
# Generate embeddings for all chunks at once
embeddings = model.encode(
    chunk_texts,
    batch_size=32,
    show_progress_bar=False
)
```

**Performance:**
- Single chunk: ~10ms
- Batch of 100: ~200ms (50x faster)

### 3. Database Indexing

```sql
-- HNSW index for vector search
CREATE INDEX job_chunks_embedding_idx
ON job_chunks USING hnsw (embedding vector_cosine_ops);

-- B-tree indexes for filtering
CREATE INDEX jobs_user_id_idx ON jobs(user_id);
CREATE INDEX jobs_status_idx ON jobs(status);
CREATE INDEX job_chunks_job_id_idx ON job_chunks(job_id);
```

### 4. Connection Pooling

```python
engine = create_async_engine(
    database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True  # Verify connections
)
```

## Security Architecture

### Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Authentik
    participant DB

    Client->>Authentik: Login (username/password)
    Authentik-->>Client: JWT Token (access_token)

    Client->>API: Request with Bearer token
    API->>API: Extract token from header
    API->>Authentik: Fetch JWKS (public keys)
    Authentik-->>API: Public keys (cached)
    API->>API: Verify JWT signature
    API->>API: Validate claims (issuer, audience, expiry)

    alt Valid Token
        API->>DB: Get or create user from JWT sub
        DB-->>API: User object with role
        API->>API: Check permissions
        API-->>Client: Success (200)
    else Invalid Token
        API-->>Client: Unauthorized (401)
    end
```

### Security Features

**1. JWT Token Verification:**
- Signature verification using Authentik's public keys
- Issuer validation
- Audience validation
- Expiration checking
- Key caching for performance

**2. Role-Based Access Control (RBAC):**
```python
# Admin-only endpoint
@app.get("/admin/users")
async def get_users(user_id: str = Depends(verify_token)):
    if not await UserService.is_admin(db, user_id):
        raise HTTPException(403, "Admin access required")
```

**3. Data Isolation:**
- Users can only access their own jobs
- Admin can access all data
- Database queries filtered by user_id

**4. SQL Injection Protection:**
- SQLAlchemy ORM with parameterized queries
- Input validation via Pydantic models

**5. CORS Configuration:**
```python
allow_origins=["*"]  # ⚠️ Configure for production
allow_credentials=True
allow_methods=["*"]
allow_headers=["*", "Authorization"]
```

**6. File Upload Security:**
- Maximum file size limit (1GB default)
- File type validation
- Temporary storage with cleanup

### Secrets Management

**Environment Variables:**
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
AUTHENTIK_CLIENT_SECRET=secret
AUTHENTIK_ADMIN_TOKEN=token
```

**Best Practices:**
- Use `.env` file (not committed to Git)
- Rotate secrets regularly
- Use secret management service (Vault, AWS Secrets Manager)

## Deployment Architecture

### Docker Compose Setup

```yaml
services:
  mxwhisper-api:
    image: mxwhisper:latest
    command: ["uv", "run", "mxwhisper"]
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL
      - AUTHENTIK_*

  mxwhisper-worker:
    image: mxwhisper:latest
    command: ["uv", "run", "mxwhisper-worker"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]
```

**Scaling:**
```bash
# Scale API servers
docker-compose up --scale mxwhisper-api=3

# Scale workers
docker-compose up --scale mxwhisper-worker=5
```

### Production Considerations

1. **Load Balancer**: Nginx or cloud load balancer
2. **Database**: Managed PostgreSQL (AWS RDS, GCP Cloud SQL)
3. **Temporal**: Self-hosted or Temporal Cloud
4. **Monitoring**: Prometheus + Grafana
5. **Logging**: Centralized logging (ELK, Loki)
6. **Backups**: Automated database backups
7. **SSL/TLS**: HTTPS for API endpoints
8. **Rate Limiting**: Prevent abuse
9. **Health Checks**: `/health` endpoint for load balancers

## Technology Stack

The following table lists all technologies used in MxWhisper with version requirements and justifications:

| Category | Technology | Version | Purpose | Justification |
|----------|-----------|---------|---------|---------------|
| **Language** | Python | 3.11+ | Application runtime | Modern async features, type hints, performance |
| **API Framework** | FastAPI | 0.119.0+ | REST API and WebSocket endpoints | Auto OpenAPI docs, async support, Pydantic validation |
| **Database** | PostgreSQL | 15+ | Primary data store | ACID compliance, robust indexing, mature ecosystem |
| **Vector DB** | pgvector | 0.3.6+ | Vector similarity search extension | Native PostgreSQL integration, HNSW index support |
| **ORM** | SQLAlchemy | 2.0.44+ | Database ORM with async support | Industry standard, async engine, type safety |
| **DB Driver** | AsyncPG | 0.30.0+ | Async PostgreSQL driver | High performance, full async/await support |
| **Workflow Engine** | Temporalio | 1.18.1+ | Distributed workflow orchestration | Durable execution, automatic retries, observability |
| **Auth** | Authentik | - | OAuth2/OIDC authentication | Self-hosted identity provider, RBAC support |
| **JWT** | Python-Jose | 3.5.0+ | JWT token handling | JWKS support, RS256 verification |
| **AI - Transcription** | OpenAI Whisper | 20250625 | Speech-to-text conversion | State-of-the-art accuracy, multilingual |
| **AI - Chunking** | vLLM / Ollama | - | LLM inference (Llama 3.1-8B) | Fast inference, semantic understanding |
| **AI - Embeddings** | SentenceTransformers | 3.3.1 | Text embedding generation | Easy to use, CPU-friendly models |
| **Embedding Model** | all-MiniLM-L6-v2 | - | 384-dim semantic vectors | Small size (80MB), fast, good accuracy |
| **Web Server** | Uvicorn | 0.37.0+ | ASGI server | High performance, graceful shutdown |
| **Migrations** | Alembic | 1.17.0+ | Database schema migrations | SQLAlchemy integration, version control |
| **HTTP Client** | HTTPX | 0.28.1+ | Async HTTP client | Async/await, timeout control, retries |
| **Logging** | Python Logging | stdlib | Structured logging | Standard library, rotating file handler |
| **Package Manager** | uv | latest | Fast Python package manager | 10-100x faster than pip, lockfile support |
| **Container Runtime** | Docker | 20.10+ | Containerization | Reproducible builds, easy deployment |
| **GPU Support** | NVIDIA CUDA | 12.4 | GPU acceleration for AI models | Faster Whisper inference, LLM acceleration |

### Why These Technologies?

**PostgreSQL + pgvector:**
- Single database for both relational and vector data
- No need for separate vector database (Pinecone, Weaviate)
- HNSW index provides fast approximate nearest neighbor search
- Reduces operational complexity

**Temporal Workflows:**
- Survives process crashes and restarts
- Built-in retry logic with exponential backoff
- Full execution history for debugging
- Heartbeat mechanism for long-running tasks
- Alternative to manual job queues (Celery, RQ)

**FastAPI:**
- Automatic OpenAPI documentation
- Type safety with Pydantic models
- Native async/await support
- Fast development with fewer bugs

**SentenceTransformers (CPU-based embeddings):**
- No GPU required for embeddings
- Fast inference (<10ms per sentence)
- Good enough accuracy for most use cases
- Allows GPU to be dedicated to Whisper

## Directory Structure

```
mxwhisper/
├── app/                          # Main application package
│   ├── auth/                     # Authentication & JWT verification
│   │   ├── __init__.py
│   │   └── jwt.py               # JWT token verification logic
│   ├── data/                     # Database layer
│   │   ├── __init__.py
│   │   ├── models.py            # SQLAlchemy models (User, Job, JobChunk, Role)
│   │   └── database.py          # DB session management & engine config
│   ├── services/                 # Business logic layer (service-oriented)
│   │   ├── __init__.py
│   │   ├── job_service.py       # Job lifecycle management
│   │   ├── user_service.py      # User & role management
│   │   ├── embedding_service.py # Vector embedding generation
│   │   └── websocket_manager.py # Real-time client notifications
│   ├── workflows/                # Temporal workflows & activities
│   │   └── transcribe/          # Transcription workflow
│   │       ├── __init__.py
│   │       ├── workflow.py      # Main workflow orchestration
│   │       ├── worker.py        # Temporal worker process
│   │       ├── activities/      # Workflow activities (async tasks)
│   │       │   ├── __init__.py
│   │       │   ├── transcribe.py # Whisper transcription activity
│   │       │   ├── chunk.py     # Semantic chunking activity
│   │       │   ├── embed.py     # Embedding generation activity
│   │       │   └── models.py    # Activity data models
│   │       ├── services/        # AI/ML service wrappers
│   │       │   ├── __init__.py
│   │       │   ├── whisper_service.py # OpenAI Whisper integration
│   │       │   └── ollama_service.py  # vLLM/Ollama LLM client
│   │       └── utils/           # Workflow utilities
│   │           ├── __init__.py
│   │           └── heartbeat.py # Progress tracking & heartbeats
│   ├── config.py                # Application configuration (Pydantic settings)
│   ├── logging_config.py        # Logging setup (console + file)
│   └── cli.py                   # CLI entry points for API & worker
├── main.py                       # FastAPI application & endpoints
├── alembic/                      # Database migrations (Alembic)
│   ├── env.py                   # Alembic environment config
│   ├── script.py.mako           # Migration template
│   └── versions/                # Versioned migration scripts
├── docker/                       # Docker configuration
│   ├── Dockerfile               # Multi-stage build with CUDA support
│   ├── docker-compose.yml       # Service orchestration (API, Worker, DB, Temporal)
│   └── verify/                  # Build verification scripts
├── tests/                        # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── test_upload.py           # Upload endpoint tests
│   ├── test_admin_api.py        # Admin endpoint tests
│   ├── test_temporal.py         # Workflow tests
│   └── data/                    # Test fixtures (audio files)
├── scripts/                      # Utility scripts
│   ├── create_admin_user.py     # Admin user creation
│   └── generate_token.py        # JWT token generation for testing
├── config/                       # Configuration templates
│   ├── .env.example             # Environment variables template
│   └── alembic.ini              # Alembic configuration
├── docs/                         # Documentation
│   ├── ARCHITECTURE.md          # Architecture documentation (this file)
│   ├── DEVELOPMENT.md           # Development guide
│   └── API.md                   # API reference
├── logs/                         # Application logs (rotating)
├── uploads/                      # Temporary audio file storage
├── pyproject.toml               # Python package definition (uv/pip)
├── README.md                    # Project overview & quick start
└── .gitignore                   # Git ignore rules
```

**Key Directory Principles:**

1. **Separation of Concerns**: Each directory has a single, well-defined purpose
2. **Layered Architecture**: Clear boundaries between API, services, workflows, and data layers
3. **Testability**: Test directory mirrors app structure for easy test discovery
4. **Configuration as Code**: All config in version control (except secrets in `.env`)
5. **Documentation Co-location**: Docs live with code for easier maintenance

## Summary

MxWhisper's architecture prioritizes:

- ✅ **Scalability**: Horizontal scaling for all components
- ✅ **Reliability**: Temporal workflows with retries and heartbeats
- ✅ **Performance**: Async operations, batch processing, optimized indexes
- ✅ **Maintainability**: Clear separation of concerns, well-defined interfaces
- ✅ **Security**: JWT authentication, RBAC, data isolation
- ✅ **Observability**: Structured logging, Temporal monitoring

The design supports growth from single-server deployment to distributed, multi-region architecture without major refactoring.
