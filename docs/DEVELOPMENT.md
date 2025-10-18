# MxWhisper Development Guide

## Table of Contents

- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Database Management](#database-management)
- [Running Tests](#running-tests)
- [Debugging](#debugging)
- [Code Style](#code-style)
- [Adding New Features](#adding-new-features)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** with pgvector extension
- **Temporal Server** (for workflow orchestration)
- **Authentik** (for authentication and user management)
  - Requires admin API token for user creation via Python SDK
- **Docker & Docker Compose** (optional, for containerized development)
- **GPU** (optional, for faster Whisper transcription)

### Initial Setup

1. **Clone the repository:**

```bash
git clone https://github.com/yourusername/mxwhisper.git
cd mxwhisper
```

2. **Install uv (Python package manager):**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. **Install dependencies:**

```bash
uv sync
```

This will create a virtual environment and install all required packages.

4. **Configure environment variables:**

```bash
cp config/.env.example .env
```

Edit `.env` with your configuration:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mxwhisper

# Temporal
TEMPORAL_HOST=localhost:7233

# Authentik (Authentication & Admin API)
AUTHENTIK_SERVER_URL=https://auth.example.com
AUTHENTIK_CLIENT_ID=your-client-id
AUTHENTIK_CLIENT_SECRET=your-client-secret
AUTHENTIK_ISSUER_URL=https://auth.example.com/application/o/mxwhisper/
AUTHENTIK_JWKS_URL=https://auth.example.com/application/o/mxwhisper/jwks/
AUTHENTIK_EXPECTED_ISSUER=https://auth.example.com/application/o/mxwhisper/
AUTHENTIK_EXPECTED_AUDIENCE=mxwhisper

# Authentik Admin API (for user management via Python SDK)
AUTHENTIK_API_URL=https://auth.example.com/api/v3
AUTHENTIK_ADMIN_TOKEN=your-admin-api-token

# Ollama/vLLM (for semantic chunking)
OLLAMA_BASE_URL=http://localhost:8000
OLLAMA_MODEL=hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4

# Whisper
WHISPER_MODEL_SIZE=base  # Options: tiny, base, small, medium, large

# Optional: Enable semantic chunking
ENABLE_SEMANTIC_CHUNKING=true
CHUNKING_STRATEGY=ollama  # Options: ollama, sentence, simple
```

5. **Setup PostgreSQL with pgvector:**

```bash
# Install pgvector extension (Ubuntu/Debian)
sudo apt install postgresql-15-pgvector

# Or use Docker
docker run -d \
  --name mxwhisper-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mxwhisper \
  -p 5432:5432 \
  pgvector/pgvector:pg15

# Enable extension
psql -U postgres -d mxwhisper -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

6. **Run database migrations:**

```bash
uv run alembic upgrade head
```

7. **Start Temporal server:**

```bash
# Using Docker
docker run -d \
  --name temporal \
  -p 7233:7233 \
  temporalio/auto-setup:latest

# Or install locally
# See: https://docs.temporal.io/docs/server/quick-install
```

8. **Start the development server:**

```bash
# Terminal 1: API server
uv run mxwhisper --reload --port 8000

# Terminal 2: Temporal worker
uv run mxwhisper-worker
```

9. **Verify setup:**

```bash
# Check API health
curl http://localhost:8000/docs

# Upload a test file (with valid JWT token)
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test.mp3"
```

## Development Environment

### Using Virtual Environment

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
uv sync

# Install development dependencies
uv sync --dev
```

### Using Docker Compose

```bash
# Start all services (PostgreSQL, Temporal, API, Worker)
docker-compose -f docker/docker-compose.yml up --build

# Stop services
docker-compose -f docker/docker-compose.yml down

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Rebuild specific service
docker-compose -f docker/docker-compose.yml up --build mxwhisper-api
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://localhost/mxwhisper` | PostgreSQL connection string |
| `TEMPORAL_HOST` | `localhost:7233` | Temporal server address |
| `UPLOAD_DIR` | `uploads` | Directory for uploaded audio files |
| `MAX_FILE_SIZE` | `1073741824` | Max upload size in bytes (1GB) |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model: tiny, base, small, medium, large |
| `ENABLE_SEMANTIC_CHUNKING` | `true` | Enable LLM-based chunking |
| `CHUNKING_STRATEGY` | `ollama` | Chunking method: ollama, sentence, simple |
| `OLLAMA_BASE_URL` | `http://localhost:8000` | vLLM/Ollama endpoint |
| `OLLAMA_MODEL` | `Meta-Llama-3.1-8B-Instruct` | LLM model for chunking |
| `ACTIVITY_HEARTBEAT_INTERVAL` | `5` | Heartbeat interval in seconds |

## Project Structure

For detailed directory structure and organization principles, see [ARCHITECTURE.md](ARCHITECTURE.md#directory-structure).

## Database Management

### Creating Migrations

```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "Add new field to Job model"

# Manually create migration
uv run alembic revision -m "Add custom index"
```

### Applying Migrations

```bash
# Upgrade to latest version
uv run alembic upgrade head

# Upgrade to specific version
uv run alembic upgrade abc123

# Downgrade one version
uv run alembic downgrade -1

# Show current version
uv run alembic current

# Show migration history
uv run alembic history
```

### Database Schema

**Tables:**
- `roles`: User roles (admin, user)
- `users`: User accounts linked to Authentik
- `jobs`: Transcription jobs
- `job_chunks`: Semantic chunks with embeddings

**Indexes:**
```sql
-- Vector similarity search (HNSW)
CREATE INDEX job_chunks_embedding_idx
ON job_chunks USING hnsw (embedding vector_cosine_ops);

-- Standard B-tree indexes
CREATE INDEX jobs_user_id_idx ON jobs(user_id);
CREATE INDEX jobs_status_idx ON jobs(status);
CREATE INDEX job_chunks_job_id_idx ON job_chunks(job_id);
```

### Seeding Test Data

```python
# scripts/seed_test_data.py
import asyncio
from app.data import async_session, Job, User, Role

async def seed():
    async with async_session() as db:
        # Create test user
        user = User(
            id="test-user-123",
            email="test@example.com",
            name="Test User",
            preferred_username="testuser",
            role_id=2
        )
        db.add(user)
        await db.commit()

asyncio.run(seed())
```

## Running Tests

### Test Structure

```
tests/
├── conftest.py                   # Pytest fixtures
├── test_upload.py                # Upload endpoint tests
├── test_admin_api.py             # Admin endpoint tests
├── test_authenticated_workflow.py # Full workflow tests
├── test_temporal.py              # Temporal workflow tests
├── test_crud.py                  # Database CRUD tests
└── data/                         # Test fixtures
    └── test_audio.mp3
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_upload.py

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run specific test
uv run pytest tests/test_upload.py::test_upload_file

# Run tests matching pattern
uv run pytest -k "admin"
```

### Writing Tests

```python
# tests/test_example.py
import pytest
from httpx import AsyncClient
from app.data import async_session, Job

@pytest.mark.asyncio
async def test_create_job(client: AsyncClient, auth_token: str):
    """Test job creation endpoint."""
    response = await client.post(
        "/upload",
        headers={"Authorization": f"Bearer {auth_token}"},
        files={"file": ("test.mp3", b"fake audio data", "audio/mpeg")}
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data

@pytest.mark.asyncio
async def test_database_query():
    """Test database operations."""
    async with async_session() as db:
        job = await db.get(Job, 1)
        assert job is not None
        assert job.status == "completed"
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.fixture
async def client():
    """HTTP client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def auth_token():
    """Mock JWT token for testing."""
    return "mock-jwt-token-for-testing"
```

## Debugging

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint (Python 3.7+)
breakpoint()

# Common pdb commands:
# n - next line
# s - step into function
# c - continue execution
# p variable - print variable
# l - list source code
# q - quit debugger
```

### Debugging with VS Code

**launch.json:**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "MxWhisper API",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "main:app",
        "--reload",
        "--port",
        "8000"
      ],
      "envFile": "${workspaceFolder}/.env",
      "console": "integratedTerminal"
    },
    {
      "name": "MxWhisper Worker",
      "type": "python",
      "request": "launch",
      "module": "app.workflows.transcribe.worker",
      "envFile": "${workspaceFolder}/.env",
      "console": "integratedTerminal"
    },
    {
      "name": "Pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["-v"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Log levels
logger.debug("Detailed information for diagnosing problems")
logger.info("Confirmation that things are working")
logger.warning("Something unexpected happened")
logger.error("Error occurred, but app continues")
logger.critical("Serious error, app may crash")

# Structured logging with context
logger.info("Job created", extra={
    "job_id": job.id,
    "user_id": user_id,
    "filename": filename
})
```

**Log Configuration:**

```python
# app/logging_config.py
from app.logging_config import setup_logging

# Text format for development
setup_logging(level="DEBUG", format_type="text", log_file="logs/debug.log")

# JSON format for production
setup_logging(level="INFO", format_type="json", log_file="logs/app.log")
```

### Monitoring Temporal Workflows

```bash
# Access Temporal Web UI
http://localhost:8233

# View workflow execution history
# Search for workflows by ID
# Inspect activity inputs/outputs
# View error stack traces
```

## Code Style

### Formatting

```bash
# Format code with Ruff
uv run ruff format .

# Check code style
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Ruff Configuration

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"]  # Errors, flake8, isort
ignore = ["E402", "E722"]  # Allow import not at top, bare except

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

### Code Conventions

1. **Type Hints**: Use type hints for all functions

```python
async def create_job(
    db: AsyncSession,
    filename: str,
    content: bytes,
    user_id: str
) -> Job:
    ...
```

2. **Docstrings**: Use Google-style docstrings

```python
async def transcribe_audio(file_path: str, job_id: int) -> dict:
    """
    Transcribe audio file using Whisper.

    Args:
        file_path: Path to audio file
        job_id: Job identifier for logging

    Returns:
        dict with 'text', 'segments', 'language'

    Raises:
        ValueError: If file doesn't exist
        RuntimeError: If transcription fails
    """
    ...
```

3. **Naming Conventions**:
   - Functions/variables: `snake_case`
   - Classes: `PascalCase`
   - Constants: `UPPER_SNAKE_CASE`
   - Private: `_leading_underscore`

4. **Imports**: Organize imports

```python
# Standard library
import asyncio
import logging
from typing import Optional

# Third-party
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Local
from app.data import Job
from app.services import JobService
```

## Adding New Features

### Adding a New API Endpoint

1. **Define request/response models** (if needed):

```python
# main.py
from pydantic import BaseModel

class NewFeatureRequest(BaseModel):
    param1: str
    param2: int

class NewFeatureResponse(BaseModel):
    result: str
```

2. **Create endpoint**:

```python
@app.post("/new-feature")
async def new_feature(
    request: NewFeatureRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """Endpoint description."""
    logger.info("New feature called", extra={"user_id": token_payload["sub"]})

    # Business logic
    result = await SomeService.do_something(db, request)

    return NewFeatureResponse(result=result)
```

3. **Add tests**:

```python
# tests/test_new_feature.py
@pytest.mark.asyncio
async def test_new_feature(client: AsyncClient, auth_token: str):
    response = await client.post(
        "/new-feature",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"param1": "value", "param2": 123}
    )

    assert response.status_code == 200
    assert response.json()["result"] == "expected"
```

### Adding a New Temporal Activity

1. **Create activity function**:

```python
# app/workflows/transcribe/activities/my_activity.py
import logging
from temporalio import activity

logger = logging.getLogger(__name__)

@activity.defn
async def my_new_activity(input_data: dict) -> dict:
    """
    New activity description.

    Args:
        input_data: Input parameters

    Returns:
        Result dictionary
    """
    logger.info("Activity started", extra={"data": input_data})

    # Activity heartbeat for long-running tasks
    activity.heartbeat("Processing...")

    # Business logic
    result = process_data(input_data)

    return {"success": True, "result": result}
```

2. **Register activity in worker**:

```python
# app/workflows/transcribe/worker.py
from .activities.my_activity import my_new_activity

worker = Worker(
    client,
    task_queue="mxwhisper-task-queue",
    workflows=[TranscribeWorkflow],
    activities=[
        transcribe_activity,
        chunk_with_ollama_activity,
        embed_chunks_activity,
        my_new_activity,  # Add new activity
    ],
)
```

3. **Use in workflow**:

```python
# app/workflows/transcribe/workflow.py
result = await workflow.execute_activity(
    "my_new_activity",
    {"param": "value"},
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=3),
)
```

### Adding a New Database Model

1. **Define model**:

```python
# app/data/models.py
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class NewModel(Base):
    __tablename__ = "new_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))

    # Relationship
    user: Mapped["User"] = relationship()
```

2. **Create migration**:

```bash
uv run alembic revision --autogenerate -m "Add new_table"
```

3. **Review and edit migration**:

```python
# alembic/versions/xxx_add_new_table.py
def upgrade():
    op.create_table(
        'new_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('new_table_user_id_idx', 'new_table', ['user_id'])

def downgrade():
    op.drop_index('new_table_user_id_idx', 'new_table')
    op.drop_table('new_table')
```

4. **Apply migration**:

```bash
uv run alembic upgrade head
```

## Deployment

### Building Docker Image

```bash
# Build with default model (base)
docker build -f docker/Dockerfile -t mxwhisper:latest .

# Build with specific Whisper model
docker build \
  --build-arg WHISPER_MODEL_SIZE=medium \
  -f docker/Dockerfile \
  -t mxwhisper:medium .

# Build without cache
docker build --no-cache -f docker/Dockerfile -t mxwhisper:latest .
```

### Deployment Checklist

- [ ] Update `.env` with production values
- [ ] Set `allow_origins` in CORS configuration
- [ ] Configure SSL/TLS certificates
- [ ] Setup managed PostgreSQL database
- [ ] Deploy Temporal server (or use Temporal Cloud)
- [ ] Configure Authentik for production
- [ ] Setup monitoring (Prometheus/Grafana)
- [ ] Configure centralized logging
- [ ] Setup automated backups
- [ ] Configure rate limiting
- [ ] Setup health check endpoints
- [ ] Configure auto-scaling
- [ ] Test disaster recovery procedures

### Environment-Specific Configs

**Development:**
```bash
ENABLE_SEMANTIC_CHUNKING=true
WHISPER_MODEL_SIZE=base
LOG_LEVEL=DEBUG
```

**Production:**
```bash
ENABLE_SEMANTIC_CHUNKING=true
WHISPER_MODEL_SIZE=medium
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/mxwhisper
TEMPORAL_HOST=temporal.prod:7233
```

## Troubleshooting

### Common Issues

**1. Database connection errors**

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution:**
- Verify PostgreSQL is running
- Check `DATABASE_URL` in `.env`
- Ensure database exists: `createdb mxwhisper`
- Check pgvector extension: `CREATE EXTENSION vector;`

**2. Temporal connection errors**

```
temporalio.service.RPCError: failed to connect to temporal server
```

**Solution:**
- Start Temporal server: `docker run -p 7233:7233 temporalio/auto-setup`
- Check `TEMPORAL_HOST` in `.env`
- Verify Temporal is listening: `telnet localhost 7233`

**3. Whisper model download fails**

```
RuntimeError: Failed to download Whisper model
```

**Solution:**
- Check internet connection
- Verify model name: `tiny`, `base`, `small`, `medium`, `large`
- Manually download: `python -c "import whisper; whisper.load_model('base')"`

**4. LLM service unavailable**

```
httpx.ConnectError: Connection refused
```

**Solution:**
- Start vLLM/Ollama server
- Check `OLLAMA_BASE_URL` in `.env`
- Activity will fallback to sentence-based chunking

**5. JWT verification fails**

```
HTTPException: Invalid token signature
```

**Solution:**
- Verify Authentik configuration
- Check `AUTHENTIK_JWKS_URL`
- Ensure token is not expired
- Verify token issuer and audience match

**6. Authentik SDK errors (user creation fails)**

```
ApiException: 1 validation error for PaginatedGroupList
```

**Solution:**
- **Version mismatch**: Ensure SDK version matches server version
- Check installed SDK: `uv pip list | grep authentik`
- Should be: `authentik-client==2024.8.2.post1726491842` for Authentik 2024.8.3
- Update version in `pyproject.toml` if needed
- Run `uv sync` to install correct version

**7. Admin API token invalid**

```
ApiException: Authentication credentials were not provided
```

**Solution:**
- Verify `AUTHENTIK_ADMIN_TOKEN` in `.env`
- Check token hasn't expired in Authentik admin UI
- Ensure token has admin privileges
- Create new token: Directory → Tokens & App passwords → Create Token

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with reload (auto-restart on code changes)
uv run mxwhisper --reload

# Verbose Temporal worker logs
uv run mxwhisper-worker --log-level debug
```

### Performance Profiling

```python
# Profile a function
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here
await slow_function()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 slowest
```

## Contributing

### Contribution Workflow

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/my-feature`
3. **Make changes** and commit: `git commit -m "Add my feature"`
4. **Write tests** for new functionality
5. **Run tests**: `uv run pytest`
6. **Format code**: `uv run ruff format .`
7. **Push changes**: `git push origin feature/my-feature`
8. **Create Pull Request**

### Pull Request Checklist

- [ ] Code follows style guidelines (Ruff)
- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated (README, docstrings)
- [ ] Database migrations included (if schema changed)
- [ ] No secrets committed (check `.env`)
- [ ] Commit messages are descriptive
- [ ] PR description explains changes

### Code Review Guidelines

**For Reviewers:**
- Check code quality and style
- Verify tests are comprehensive
- Ensure documentation is clear
- Test locally if possible
- Provide constructive feedback

**For Contributors:**
- Address review comments
- Keep PR focused on single feature
- Rebase on latest main before merging
- Squash commits if requested

## Development Best Practices

1. **Always use type hints**
2. **Write tests first (TDD)**
3. **Keep functions small and focused**
4. **Use async/await consistently**
5. **Log important events with context**
6. **Handle errors gracefully**
7. **Document complex logic**
8. **Review your own code before PR**
9. **Run tests before committing**
10. **Keep dependencies up to date**

---

## Authentik Integration

### Authentik Python SDK

MxWhisper uses the **official Authentik Python SDK** (`authentik-client`) for admin operations like user creation and group management.

**SDK Version:**
- Package: `authentik-client==2024.8.2.post1726491842`
- Must match your Authentik server version (2024.8.x compatible with 2024.8.3 server)

**What the SDK is used for:**
- Creating users programmatically
- Assigning users to groups
- Setting passwords
- Looking up group UUIDs by name

**Implementation:**
- Located in [`app/auth/authentik.py`](../app/auth/authentik.py)
- Uses `asyncio.to_thread()` wrapper for async compatibility
- Type-safe operations with `UserRequest` and other Pydantic models
- Automatic error handling with `ApiException`

### Creating Service Accounts (API Users)

Use the provided script to create service accounts with non-expiring JWT tokens:

```bash
# Create regular user service account
uv run python scripts/create_api_user.py \
  --username api-service \
  --email service@example.com \
  --role user

# Create admin service account
uv run python scripts/create_api_user.py \
  --username api-admin \
  --email admin@example.com \
  --role admin
```

**The script will:**
1. Create user in Authentik via Python SDK
2. Assign user to appropriate groups (`users`, `admin.mxwhisper`)
3. Create user record in local database
4. Generate non-expiring JWT token for API access

**Example output:**
```
✅ Service account created successfully!
   User ID: 34
   Username: api-service
   Email: service@example.com
   Role: user

🔑 Non-expiring JWT token:
================================================================================
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
================================================================================
```

### Admin User Setup

#### Manual Authentik Group Configuration

**You need to do this manually in the Authentik web UI:**

1. **Log into Authentik Admin**: `http://authentik.yourdomain.net/if/admin/`
2. **Create Groups** (if not already created):
   - Directory → Groups → Create
   - Name: `users` (for all users)
   - Name: `admin.mxwhisper` (for admin access)
3. **Get Admin API Token**:
   - Directory → Tokens & App passwords → Create Token
   - User: Select admin user
   - Intent: API Token
   - Expires: Never (or set appropriate expiry)
   - Copy token and add to `.env` as `AUTHENTIK_ADMIN_TOKEN`
4. **Add Admin Users**:
   - Directory → Users → Select user → Groups tab → Add to `admin.mxwhisper` group
5. **Test JWT Token**:
   - Login with admin user
   - JWT should contain: `"groups": ["admin.mxwhisper", ...]`

### Setting Up a Specific Admin User

For better organization, create a dedicated admin user in Authentik:

1. **Create User in Authentik**:
   - Directory → Users → Create
   - Username: `admin.mxwhisper` (or your preferred naming)
   - Email: `admin@yourdomain.com`
   - Set a strong password

2. **Add to Admin Group**:
   - Select the user → Groups tab
   - Add to the `admin` group you created earlier

3. **Test Admin Access**:
   - Login as `admin.mxwhisper`
   - JWT token will include `"groups": ["admin", ...]`
   - Access admin endpoints: `/admin/users`, `/admin/jobs`

### Why Not Create Default Admin Users?

**Security Best Practice**: The application does NOT create default admin users because:

- ❌ **Security Risk**: Predefined admin accounts are common attack targets
- ❌ **No Password Management**: Authentik handles passwords, not the app
- ✅ **Group-Based Access**: Admin access via Authentik groups is more secure
- ✅ **Flexible**: Multiple users can be admins by adding them to the group

### Testing Admin Functionality

Run the test script to verify role assignment:

```bash
uv run python tests/test_admin_setup.py
```

This will:
- ✅ Test role initialization
- ✅ Test user creation with different group memberships
- ✅ Show mock JWT tokens for testing
- ✅ Provide detailed Authentik setup instructions

### Manual API Testing

After setting up Authentik groups:

```bash
# Start the server
uv run mxwhisper --reload --port 8000

# Test admin endpoints with real JWT tokens from Authentik
curl -H "Authorization: Bearer <admin-jwt-token>" http://localhost:8000/admin/jobs
curl -H "Authorization: Bearer <admin-jwt-token>" http://localhost:8000/admin/users

# Test regular user access (should fail with 403)
curl -H "Authorization: Bearer <regular-jwt-token>" http://localhost:8000/admin/users
```

### Alternative Group Names

The app recognizes these group names as admin:
- `admin.mxwhisper` (recommended)
- `mxwhisper-admin`
- `admin`
- `administrators`
- `Admins`

## Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **Temporal Documentation**: https://docs.temporal.io
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org
- **pgvector Documentation**: https://github.com/pgvector/pgvector
- **Whisper Documentation**: https://github.com/openai/whisper
- **MxWhisper Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **MxWhisper API Reference**: [API.md](API.md)

For questions or support, please open an issue on GitHub.
