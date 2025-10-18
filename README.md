# MxWhisper

A production-ready transcription service with AI-powered semantic search capabilities. Built with FastAPI, Temporal workflows, OpenAI Whisper, and PostgreSQL with pgvector for intelligent audio-to-text conversion and semantic search.

## Overview

MxWhisper is a scalable audio transcription platform that combines:

- **Audio Transcription**: OpenAI Whisper models for accurate speech-to-text conversion
- **Semantic Chunking**: LLM-powered topic analysis to create meaningful content segments
- **Vector Search**: pgvector-powered semantic search across transcripts
- **Workflow Orchestration**: Temporal for reliable, long-running background tasks
- **Real-time Updates**: WebSocket support for live progress tracking
- **Enterprise Auth**: Authentik integration with JWT and RBAC

## Quick Start

### Using Docker (Recommended)

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure environment**:
   ```bash
   cp config/.env.example .env
   # Edit .env with your configuration
   ```

3. **Build and deploy**:
   ```bash
   # Build with default Whisper model (base)
   ./build-image.sh

   # Start all services
   ./deploy.sh

   # Or build and start in one command
   ./deploy.sh --build
   ```

4. **Verify setup**:
   ```bash
   # Check API health
   curl http://localhost:8000/docs
   ```

### Configuration Options

**Whisper Model Sizes** (set `WHISPER_MODEL_SIZE` in `.env`):
- `tiny` (~40MB): Fastest, lowest accuracy - good for testing
- `base` (~140MB): **Default** - balanced speed and accuracy
- `small` (~480MB): Better accuracy, slower
- `medium` (~1.5GB): High accuracy, requires more VRAM
- `large` (~3GB): Best accuracy, slowest, highest VRAM requirement

**Build with specific model**:
```bash
docker build -f docker/Dockerfile --build-arg WHISPER_MODEL_SIZE=medium -t mxwhisper:latest .
```

## Key Features

### AI-Powered Semantic Search

Search transcripts by **meaning**, not just keywords:

```bash
curl -X POST "http://localhost:8000/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "biblical teachings about the Messiah",
    "limit": 10
  }'
```

**Example Searches**:
- Query: `"biblical teachings"` → Finds: scripture, gospel, Christ, holy texts
- Query: `"love and compassion"` → Finds: mercy, kindness, caring, empathy
- Query: `"God's anointed"` → Finds: Messiah, Christ, chosen one

**How It Works**:
1. Audio transcribed with Whisper
2. Text converted to 384-dim vectors using SentenceTransformers
3. Vectors stored in PostgreSQL with pgvector extension
4. HNSW index enables fast similarity search

### Real-time Progress Tracking

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/jobs/${jobId}`);
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(`Status: ${update.status}, Progress: ${update.progress}%`);
};
```

### Workflow Pipeline

```
Upload Audio → Transcribe (Whisper) → Semantic Chunking (LLM) → Generate Embeddings → Search
```

## API Endpoints

### User Endpoints
- `POST /upload` - Upload audio file for transcription
- `GET /jobs/{id}` - Get job status
- `GET /jobs/{id}/download` - Download transcript (TXT/SRT)
- `GET /user/jobs` - Get all user's jobs
- `POST /search` - Semantic search across transcripts

### Admin Endpoints
- `GET /admin/jobs` - Get all jobs (all users)
- `GET /admin/users` - Get all users and roles

### Real-time
- `WebSocket /ws/jobs/{id}` - Real-time job updates

For detailed API documentation, see [API.md](docs/API.md) or visit `http://localhost:8000/docs` for interactive Swagger UI.

## Authentication

MxWhisper uses JWT tokens issued by Authentik for authentication. All endpoints (except WebSocket) require a valid JWT token in the `Authorization` header:

```bash
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Roles**:
- **User**: Can upload files and view their own jobs
- **Admin**: Can view all jobs and users across the system

For detailed authentication setup, see [DEVELOPMENT.md](docs/DEVELOPMENT.md#admin-user-setup).

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Framework | FastAPI | REST API and WebSocket endpoints |
| Database | PostgreSQL 15+ | Primary data store |
| Vector Search | pgvector | Semantic similarity search |
| Workflow Engine | Temporal | Distributed workflow orchestration |
| Authentication | Authentik | OAuth2/OIDC identity provider |
| AI - Transcription | OpenAI Whisper | Speech-to-text conversion |
| AI - Chunking | vLLM/Ollama (Llama 3.1-8B) | Semantic topic analysis |
| AI - Embeddings | SentenceTransformers | Text embedding generation |

For detailed technology decisions and architecture, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        UI[Web/Mobile Client]
    end

    subgraph "API Layer"
        FastAPI[FastAPI Server]
        WS[WebSocket Handler]
    end

    subgraph "Service Layer"
        JobSvc[Job Service]
        UserSvc[User Service]
        EmbedSvc[Embedding Service]
    end

    subgraph "Workflow Layer - Temporal"
        Workflow[Transcribe Workflow]
        TransAct[Transcribe Activity<br/>Whisper]
        ChunkAct[Chunk Activity<br/>LLM]
        EmbedAct[Embed Activity<br/>SentenceTransformers]
    end

    subgraph "Data Layer"
        Postgres[(PostgreSQL + pgvector)]
    end

    subgraph "Auth Layer"
        Authentik[Authentik<br/>OAuth2/OIDC]
    end

    UI -->|HTTP/WS| FastAPI
    FastAPI -->|Auth| Authentik
    FastAPI --> JobSvc
    FastAPI --> UserSvc
    JobSvc -->|Trigger| Workflow
    Workflow --> TransAct
    Workflow --> ChunkAct
    Workflow --> EmbedAct
    TransAct --> Postgres
    ChunkAct --> Postgres
    EmbedAct --> Postgres

    style FastAPI fill:#4A90E2
    style Workflow fill:#F5A623
    style Postgres fill:#50C878
    style Authentik fill:#E94B3C
```

**Design Principles**:
- **Layered Architecture**: Clear separation of concerns
- **Async-First**: Full async/await throughout the stack
- **Event-Driven**: Temporal workflows for reliable async processing
- **Stateless API**: Horizontal scaling support
- **Database as Source of Truth**: PostgreSQL stores all state

For detailed architecture documentation, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

### Local Setup

```bash
# Install dependencies
uv sync

# Copy environment file
cp config/.env.example .env

# Run database migrations
uv run alembic upgrade head

# Start API server
uv run mxwhisper --reload --port 8000

# Start Temporal worker (in another terminal)
uv run mxwhisper-worker
```

### Database Requirements

- **PostgreSQL 15+** with **pgvector extension**
- For Kubernetes: Use `pgvector/pgvector:pg15` image
- For Docker: See [docker-compose.yml](docker/docker-compose.yml)

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

For detailed development instructions, see [DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Deployment

### Docker Compose (Production)

```bash
# Build with specific Whisper model
docker build -f docker/Dockerfile --build-arg WHISPER_MODEL_SIZE=medium -t mxwhisper:latest .

# Start services
./deploy.sh

# Scale workers
docker-compose up --scale mxwhisper-worker=5
```

### Environment Variables

Key configuration options:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/mxwhisper

# Temporal
TEMPORAL_HOST=localhost:7233

# Authentik
AUTHENTIK_SERVER_URL=https://auth.example.com
AUTHENTIK_CLIENT_ID=your-client-id
AUTHENTIK_CLIENT_SECRET=your-secret

# AI Configuration
WHISPER_MODEL_SIZE=base
OLLAMA_BASE_URL=http://localhost:8000
ENABLE_SEMANTIC_CHUNKING=true
```

For complete configuration options, see [DEVELOPMENT.md](docs/DEVELOPMENT.md#environment-variables).

## Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Detailed architecture, design patterns, and technology decisions
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Development setup, testing, and contributing guidelines
- **[API.md](docs/API.md)** - Complete API reference with examples

## Use Cases

- **Podcast Transcription**: Convert episodes to searchable text
- **Meeting Notes**: Transcribe meetings with semantic search
- **Lecture Archives**: Search educational content by topic
- **Interview Analysis**: Find key topics across interviews
- **Content Accessibility**: Generate subtitles and captions

## License

[Your License Here]

## Support

For questions or issues, please open an issue on GitHub.
