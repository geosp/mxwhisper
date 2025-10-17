# MxWhisper

A full-stack transcription service with AI-powered semantic search using FastAPI, Temporal, Whisper, and pgvector.

## Architecture

The application follows a modular architecture with separated concerns:

- **API Layer** (`main.py`): FastAPI endpoints and WebSocket handling
- **Services Layer** (`app/services/`): Business logic separated by domain
  - `user_service.py`: User management, authentication, and role handling
  - `job_service.py`: Job management and workflow orchestration
  - `embedding_service.py`: AI-powered semantic embeddings for search
- **Data Layer** (`app/database.py`): SQLAlchemy models with pgvector support for semantic search
- **Workflow Layer** (`app/workflows/`): Temporal workflow definitions and activities
- **Configuration** (`app/config.py`, `app/logging_config.py`): Application settings and logging

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Copy environment file:
   ```bash
   cp config/.env.example .env
   ```

3. Configure Whisper model (optional):

   Edit `.env` and set the desired model size:
   ```bash
   WHISPER_MODEL_SIZE=base  # Options: tiny, base, small, medium, large
   ```

   **Model size comparison:**
   - `tiny` (~40MB): Fastest, lowest accuracy - good for testing
   - `base` (~140MB): **Default** - balanced speed and accuracy
   - `small` (~480MB): Better accuracy, slower
   - `medium` (~1.5GB): High accuracy, requires more VRAM
   - `large` (~3GB): Best accuracy, slowest, highest VRAM requirement

4. Build and run with Docker:
   ```bash
   # Build with default model (base)
   ./build-image.sh

   # Build with a specific model (e.g., medium)
   docker build -f docker/Dockerfile --build-arg WHISPER_MODEL_SIZE=medium -t mxwhisper:latest .

   # Start the services
   ./deploy.sh

   # Or do both in one command
   ./deploy.sh --build
   ```

   Alternative commands:
   ```bash
   # Stop services
   ./deploy.sh --down

   # Start and show logs
   ./deploy.sh --logs

   # Show only API logs
   ./deploy.sh --logs --service api

   # Build without cache
   ./build-image.sh --no-cache
   ```

   **Note:** The Whisper model is preloaded during Docker build, so the first transcription will start immediately without downloading the model.

## API Endpoints

All endpoints except WebSocket require JWT authentication via `Authorization: Bearer <token>` header.

### User Endpoints
- `POST /upload` - Upload audio file for transcription (requires auth)
- `GET /jobs/{id}` - Get job status (requires auth)
- `GET /jobs/{id}/download` - Download completed transcript (requires auth)
- `GET /user/jobs` - Get all jobs for authenticated user (requires auth)
- `POST /search` - Semantic search across transcripts (requires auth)

### Admin Endpoints (Admin role required)
- `GET /admin/jobs` - Get all jobs across all users (admin only)
- `GET /admin/users` - Get all users and their roles (admin only)

### Real-time Updates
- `WebSocket /ws/jobs/{id}` - Real-time job status updates (no auth required)

## Semantic Search

MxWhisper includes AI-powered semantic search that allows you to find transcripts by **meaning**, not just exact keywords.

### How It Works

1. **Audio Transcription**: Whisper converts audio to text
2. **Embedding Generation**: Text is converted to 384-dimensional vectors using sentence-transformers (`all-MiniLM-L6-v2` model)
3. **Vector Storage**: Embeddings are stored in PostgreSQL with pgvector extension
4. **Similarity Search**: HNSW index enables fast approximate nearest neighbor search using cosine similarity

### Features

- **Semantic Understanding**: Search "biblical teachings" to find "scripture", "gospel", "Christ"
- **Fast & Scalable**: HNSW indexing for O(log n) search performance
- **Privacy-First**: All processing happens locally - no external API calls
- **User-Scoped**: Each user only searches their own transcripts

### API Usage

**Request:**
```bash
curl -X POST "http://localhost:8000/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "biblical teachings about the Messiah",
    "limit": 10
  }'
```

**Response:**
```json
{
  "query": "biblical teachings about the Messiah",
  "results": [
    {
      "job_id": 15,
      "filename": "sermon.mp3",
      "preview": "The Bible also calls Him the Christ, the Greek word for Messiah, which means God's anointed one...",
      "similarity": 0.89,
      "created_at": "2025-10-17T10:30:00"
    }
  ]
}
```

### Search Examples

**Traditional Keyword Search** (limited):
- Query: "God's anointed" → Only finds exact matches

**Semantic Search** (intelligent):
- Query: "God's anointed" → Finds "Messiah", "Christ", "Jesus"
- Query: "love and compassion" → Finds "mercy and kindness"
- Query: "ancient scriptures" → Finds "biblical texts", "holy writings"
- Query: "spiritual leader" → Finds "pastor", "minister", "priest"

### Technical Details

- **Model**: `all-MiniLM-L6-v2` (80MB, runs on CPU, very fast)
- **Vector Dimensions**: 384 (optimal balance of speed/accuracy)
- **Distance Metric**: Cosine similarity (best for semantic search)
- **Index Type**: HNSW (Hierarchical Navigable Small World)
- **PostgreSQL Extension**: pgvector 0.8.1+

## Development

- Run migrations: `uv run alembic upgrade head`
- Start server: `uv run mxwhisper`
- Run worker: `uv run mxwhisper-worker`

### Logging

The application uses structured logging with both console and file output:
- **Log files**: Located in `logs/mxwhisper.log` (rotating, 10MB max per file, 5 backups)
- **Log levels**: INFO (default), DEBUG, WARNING, ERROR, CRITICAL
- **Format**: Text format for readability, JSON format available for production
- **External libraries**: SQLAlchemy, Temporal, and HTTPX noise is reduced

To change log level: Modify the `setup_logging()` call in `main.py`

## Database Initialization

For first-time setup:

1. **Start the services** (this creates the PostgreSQL database):
   ```bash
   docker/docker-compose up -d db
   ```

2. **Run migrations** to create tables:
   ```bash
   uv run alembic upgrade head
   ```

3. **Start the full stack**:
   ```bash
   docker/docker-compose up --build
   ```

The database schema is managed through Alembic migrations. The initial migration creates the `jobs` table with all necessary columns. Subsequent changes to the model will generate new migrations automatically.

For development without Docker, ensure PostgreSQL is running locally and update `DATABASE_URL` in your `.env` file.

## Database Setup

### Requirements

- **PostgreSQL 15+** with **pgvector extension** installed
- For semantic search to work, the pgvector extension must be available

### PostgreSQL with pgvector

**For Kubernetes Deployments:**

Use the official pgvector PostgreSQL image in your deployment:
```yaml
postgresql_image: "pgvector/pgvector:pg15"
```

Then enable the extension on your database:
```bash
# Enable pgvector extension (requires superuser privileges)
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U postgres -d mxwhisper -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Verify installation
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U postgres -d mxwhisper -c "\dx vector"
```

**For Docker/Local Development:**

If using standard PostgreSQL, install pgvector:
```bash
# Ubuntu/Debian
sudo apt install postgresql-15-pgvector

# Then in psql:
CREATE EXTENSION IF NOT EXISTS vector;
```

Or use the Docker image:
```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg15
```

### Running Migrations

1. **Ensure PostgreSQL database exists** with the credentials in your `.env` file
2. **Ensure pgvector extension is enabled** (see above)
3. **Run migrations** to create tables and vector columns:
   ```bash
   uv run alembic -c config/alembic.ini upgrade head
   ```

This will create:
- Database tables (jobs, users, roles)
- Vector column for embeddings (384 dimensions)
- HNSW index for fast similarity search

## Authentication

The API uses JWT tokens issued by Authentik for authentication. Tokens must be included in the `Authorization` header as `Bearer <token>`.

### Configuration

Set the following environment variables in your `.env` file:

- `AUTHENTIK_SERVER_URL`: Base URL of your Authentik instance
- `AUTHENTIK_CLIENT_ID`: OAuth2 client ID
- `AUTHENTIK_CLIENT_SECRET`: OAuth2 client secret
- `AUTHENTIK_ISSUER_URL`: Token issuer URL
- `AUTHENTIK_JWKS_URL`: JWKS endpoint for public key verification
- `AUTHENTIK_EXPECTED_ISSUER`: Expected issuer claim in tokens
- `AUTHENTIK_EXPECTED_AUDIENCE`: Expected audience claim in tokens
- `AUTHENTIK_SCOPES`: OAuth scopes (default: "openid profile email")

The application automatically fetches and caches Authentik's public keys for token verification.

### Roles and Permissions

The application supports role-based access control:

- **User**: Can upload files and view their own jobs
- **Admin**: Can view all jobs and users across the system

Admin roles are determined by Authentik groups. Users with groups containing "admin", "administrators", or "Admins" are automatically assigned admin role.

Default roles are created automatically on application startup.

## Admin Setup and Testing

### Manual Authentik Group Configuration

**You need to do this manually in the Authentik web UI:**

1. **Log into Authentik Admin**: `http://authentik.mixwarecs-home.net/if/admin/`
2. **Create Admin Group**:
   - Directory → Groups → Create
   - Name: `admin.mxwhisper` (recommended for consistency)
   - Add users who should have admin access
3. **Add Admin Users**:
   - Directory → Users → Select user → Groups tab → Add to admin group
4. **Test JWT Token**:
   - Login with admin user
   - JWT should contain: `"groups": ["admin", ...]`

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
uv run mxwhisper --reload --port 3001

# Test admin endpoints with real JWT tokens from Authentik
curl -H "Authorization: Bearer <admin-jwt-token>" http://localhost:3001/admin/jobs
curl -H "Authorization: Bearer <admin-jwt-token>" http://localhost:3001/admin/users

# Test regular user access (should fail)
curl -H "Authorization: Bearer <regular-jwt-token>" http://localhost:3001/admin/users
```

7. Alternative Group Names:
   The app recognizes these group names as admin:
   - "admin.mxwhisper" (recommended)
   - "mxwhisper-admin"
   - "admin"
   - "administrators"
   - "Admins"