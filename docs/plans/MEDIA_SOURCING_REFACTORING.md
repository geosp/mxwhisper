# Media Sourcing & Job/Transcription Separation - Refactoring Plan

**Status**: Draft
**Created**: 2025-10-19
**Owner**: Architecture Team

## Executive Summary

This document outlines a comprehensive refactoring of MxWhisper to:

1. **Separate Concerns**: Decouple job orchestration from domain entities (transcriptions)
2. **Multi-Source Media**: Support local uploads and URL downloads via yt-dlp
3. **User Organization**: Implement user-specific folder structures
4. **Deduplication**: Use checksum-based duplicate detection
5. **Clean Architecture**: Start with clean schema (no data migration)

### Key Principles

- ✅ **Clean Start**: No data migration from old jobs table
- ✅ **Separation of Concerns**: Jobs = workflow orchestration, AudioFiles = media storage, Transcriptions = domain entities
- ✅ **Separate Workflows**: Download and transcribe are independent operations
- ✅ **User Control**: Users explicitly trigger transcription after download
- ✅ **Flexibility**: Support all yt-dlp sources (not just YouTube)
- ✅ **Deduplication**: SHA256 checksums prevent duplicate uploads
- ✅ **Audio Only**: Extract audio, no metadata storage
- ✅ **Indefinite Retention**: Keep files forever, no storage limits

---

## 1. Database Schema Changes

### 1.1 New Tables

#### audio_files
Stores all media files with ownership, checksums, and source information.

```sql
CREATE TABLE audio_files (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- File storage
    file_path VARCHAR(1000) NOT NULL,              -- uploads/user_30/2025/10/checksum_file.mp3
    original_filename VARCHAR(500) NOT NULL,        -- Original uploaded/downloaded filename
    file_size BIGINT NOT NULL,                      -- Bytes
    mime_type VARCHAR(100),                         -- audio/mpeg, audio/wav, etc.
    duration FLOAT,                                 -- Seconds (extracted from audio)

    -- Deduplication
    checksum VARCHAR(64) NOT NULL,                  -- SHA256 hash

    -- Source tracking
    source_type VARCHAR(50) NOT NULL,               -- 'upload' | 'download'
    source_url TEXT,                                -- Original URL if downloaded
    source_platform VARCHAR(100),                   -- 'youtube', 'soundcloud', etc. (extracted from URL)

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Indexes
    CONSTRAINT uq_user_checksum UNIQUE (user_id, checksum)
);

CREATE INDEX idx_audio_files_user_id ON audio_files(user_id);
CREATE INDEX idx_audio_files_checksum ON audio_files(checksum);
CREATE INDEX idx_audio_files_source_type ON audio_files(source_type);
CREATE INDEX idx_audio_files_created_at ON audio_files(created_at DESC);
```

#### transcriptions
Domain entity representing transcription results (decoupled from jobs).

```sql
CREATE TABLE transcriptions (
    id SERIAL PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Transcription content
    transcript TEXT NOT NULL,                       -- Full plaintext transcript
    language VARCHAR(10),                           -- Detected/specified language code

    -- Model information
    model_name VARCHAR(100),                        -- 'whisper-large-v3', etc.
    model_version VARCHAR(50),

    -- Quality metrics
    avg_confidence FLOAT,                           -- Average confidence across segments
    processing_time FLOAT,                          -- Seconds taken to transcribe

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending' | 'processing' | 'completed' | 'failed'
    error_message TEXT,                             -- If status = 'failed'

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Indexes
    CONSTRAINT fk_audio_file FOREIGN KEY (audio_file_id) REFERENCES audio_files(id) ON DELETE CASCADE
);

CREATE INDEX idx_transcriptions_audio_file ON transcriptions(audio_file_id);
CREATE INDEX idx_transcriptions_user_id ON transcriptions(user_id);
CREATE INDEX idx_transcriptions_status ON transcriptions(status);
CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at DESC);
```

#### transcription_chunks
Replaces `job_chunks` - stores segments with embeddings for semantic search.

```sql
CREATE TABLE transcription_chunks (
    id SERIAL PRIMARY KEY,
    transcription_id INTEGER NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,

    -- Chunk content
    chunk_index INTEGER NOT NULL,                   -- Sequential order within transcription
    text TEXT NOT NULL,                             -- Chunk text content

    -- Topic analysis (optional, for AI integration)
    topic_summary TEXT,                             -- AI-generated topic summary
    keywords VARCHAR[] DEFAULT '{}',                -- Extracted keywords
    confidence FLOAT,                               -- AI confidence score

    -- Temporal alignment
    start_time FLOAT,                               -- Seconds from start
    end_time FLOAT,                                 -- Seconds from start

    -- Character positions (for text highlighting)
    start_char_pos INTEGER,                         -- Position in full transcript
    end_char_pos INTEGER,                           -- Position in full transcript

    -- Semantic search
    embedding VECTOR(384),                          -- pgvector embedding

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_transcription_chunk UNIQUE (transcription_id, chunk_index)
);

CREATE INDEX idx_transcription_chunks_transcription ON transcription_chunks(transcription_id);
CREATE INDEX idx_transcription_chunks_embedding ON transcription_chunks USING ivfflat (embedding vector_cosine_ops);
```

#### transcription_topics
Junction table linking transcriptions to topics (replaces job_topics).

```sql
CREATE TABLE transcription_topics (
    id SERIAL PRIMARY KEY,
    transcription_id INTEGER NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,

    -- AI assignment tracking
    ai_confidence FLOAT,                            -- AI confidence score (0.0-1.0)
    ai_reasoning TEXT,                              -- Why AI assigned this topic

    -- User assignment tracking
    assigned_by VARCHAR(255) REFERENCES users(id),  -- NULL if AI-assigned
    user_reviewed BOOLEAN DEFAULT FALSE,            -- User confirmed/rejected

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_transcription_topic UNIQUE (transcription_id, topic_id)
);

CREATE INDEX idx_transcription_topics_transcription ON transcription_topics(transcription_id);
CREATE INDEX idx_transcription_topics_topic ON transcription_topics(topic_id);
CREATE INDEX idx_transcription_topics_ai_confidence ON transcription_topics(ai_confidence);
```

#### transcription_collections
Junction table linking transcriptions to collections (replaces job_collections).

```sql
CREATE TABLE transcription_collections (
    id SERIAL PRIMARY KEY,
    transcription_id INTEGER NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,

    position INTEGER,                               -- Order within collection
    assigned_by VARCHAR(255) REFERENCES users(id),  -- Who added to collection

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_transcription_collection UNIQUE (transcription_id, collection_id)
);

CREATE INDEX idx_transcription_collections_transcription ON transcription_collections(transcription_id);
CREATE INDEX idx_transcription_collections_collection ON transcription_collections(collection_id);
CREATE INDEX idx_transcription_collections_position ON transcription_collections(position);
```

### 1.2 Jobs Table Updates

Update existing `jobs` table to support polymorphic job types:

```sql
ALTER TABLE jobs ADD COLUMN job_type VARCHAR(50) NOT NULL DEFAULT 'transcription';
ALTER TABLE jobs ADD COLUMN audio_file_id INTEGER REFERENCES audio_files(id) ON DELETE SET NULL;
ALTER TABLE jobs ADD COLUMN source_url TEXT;

CREATE INDEX idx_jobs_job_type ON jobs(job_type);
CREATE INDEX idx_jobs_audio_file_id ON jobs(audio_file_id);

-- Job types: 'download', 'transcription'
-- For download jobs: source_url is populated
-- For transcription jobs: audio_file_id is populated
```

---

## 2. User Folder Structure

### 2.1 Directory Organization

```
uploads/
├── user_{user_id}/
│   ├── 2025/
│   │   ├── 10/
│   │   │   ├── {checksum}_original_filename.mp3
│   │   │   ├── {checksum}_another_file.wav
│   │   │   └── {checksum}_downloaded_audio.m4a
│   │   ├── 11/
│   │   │   └── ...
│   └── temp/                          # Temporary downloads (cleaned up after processing)
│       └── {uuid}_temp_download.part
└── shared/                             # Optional: publicly shared audio files
```

### 2.2 Path Generation Logic

**Service**: `AudioFileService.generate_file_path()`

```python
def generate_file_path(user_id: str, original_filename: str, checksum: str) -> str:
    """
    Generate user-specific file path with date-based organization.

    Returns: uploads/user_{user_id}/YYYY/MM/{checksum}_{sanitized_filename}.{ext}
    """
    now = datetime.utcnow()
    year = now.strftime("%Y")
    month = now.strftime("%m")

    # Sanitize filename (remove special chars, limit length)
    safe_filename = sanitize_filename(original_filename)
    name, ext = os.path.splitext(safe_filename)

    # Truncate name if too long (max 200 chars)
    if len(name) > 200:
        name = name[:200]

    filename = f"{checksum[:16]}_{name}{ext}"

    return f"uploads/user_{user_id}/{year}/{month}/{filename}"
```

### 2.3 Checksum Deduplication

**Service**: `AudioFileService.calculate_checksum()`

```python
async def calculate_checksum(file_path: str) -> str:
    """
    Calculate SHA256 checksum for deduplication.
    Reads file in chunks to handle large files efficiently.
    """
    sha256 = hashlib.sha256()

    async with aiofiles.open(file_path, 'rb') as f:
        while chunk := await f.read(8192):  # 8KB chunks
            sha256.update(chunk)

    return sha256.hexdigest()
```

**Deduplication Flow**:

1. User uploads file → calculate checksum
2. Check `audio_files` table for existing `(user_id, checksum)` pair
3. If exists → return existing `AudioFile` record (no file copy)
4. If new → save file to user folder, create `AudioFile` record

---

## 3. Service Layer Architecture

### 3.1 AudioFileService

**Location**: `app/services/audio_file_service.py`

**Responsibilities**:
- File upload handling
- Checksum calculation and deduplication
- User folder creation and management
- File metadata extraction (duration, mime type)
- File retrieval and deletion

**Key Methods**:

```python
class AudioFileService:
    @staticmethod
    async def create_from_upload(
        db: AsyncSession,
        user_id: str,
        uploaded_file: UploadFile
    ) -> AudioFile:
        """
        Handle local file upload with deduplication.

        1. Save to temp location
        2. Calculate checksum
        3. Check for duplicate
        4. Move to user folder (if new)
        5. Create AudioFile record
        """
        pass

    @staticmethod
    async def create_from_download(
        db: AsyncSession,
        user_id: str,
        source_url: str,
        downloaded_file_path: str,
        original_filename: str
    ) -> AudioFile:
        """
        Create AudioFile from downloaded file (via yt-dlp).

        Similar to create_from_upload but source_type='download'.
        """
        pass

    @staticmethod
    async def get_user_files(
        db: AsyncSession,
        user_id: str,
        source_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[AudioFile]:
        """
        List user's audio files with pagination and filtering.
        """
        pass

    @staticmethod
    async def delete_file(
        db: AsyncSession,
        audio_file_id: int,
        user_id: str
    ) -> None:
        """
        Delete audio file (permission check + file removal).
        Cascade deletes transcriptions via FK constraint.
        """
        pass

    @staticmethod
    async def extract_metadata(file_path: str) -> Dict[str, Any]:
        """
        Extract audio metadata (duration, sample rate, etc.).
        Uses ffprobe or similar tool.
        """
        pass
```

### 3.2 DownloadService

**Location**: `app/services/download_service.py`

**Responsibilities**:
- yt-dlp integration for URL downloads
- Platform detection (YouTube, SoundCloud, etc.)
- Audio extraction configuration
- Download progress tracking (optional)
- Error handling for unsupported URLs

**Key Methods**:

```python
class DownloadService:
    @staticmethod
    async def download_audio(
        source_url: str,
        output_path: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Download audio from URL using yt-dlp.

        Returns:
            {
                "file_path": "path/to/downloaded.mp3",
                "original_filename": "Video Title.mp3",
                "platform": "youtube",
                "duration": 3600.5
            }

        yt-dlp config:
            - Extract audio only (--extract-audio)
            - Best audio quality (--audio-quality 0)
            - Prefer m4a/mp3 format
            - No metadata files
            - No thumbnail downloads
        """
        pass

    @staticmethod
    def detect_platform(url: str) -> str:
        """
        Detect platform from URL (youtube, soundcloud, vimeo, etc.).
        """
        pass

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL is supported by yt-dlp.
        """
        pass
```

**yt-dlp Configuration**:

```python
YT_DLP_OPTS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'audioquality': 0,  # Best quality
    'outtmpl': '%(id)s.%(ext)s',  # Use video ID as filename
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'writethumbnail': False,
    'writesubtitles': False,
    'writeinfojson': False,  # No metadata files
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}
```

### 3.3 TranscriptionService

**Location**: `app/services/transcription_service.py`

**Responsibilities**:
- Create transcription records
- Manage transcription status
- Link to topics and collections
- Chunk management
- Embedding generation

**Key Methods**:

```python
class TranscriptionService:
    @staticmethod
    async def create_transcription(
        db: AsyncSession,
        audio_file_id: int,
        user_id: str
    ) -> Transcription:
        """
        Create new transcription record.
        Status starts as 'pending'.
        """
        pass

    @staticmethod
    async def update_transcription_result(
        db: AsyncSession,
        transcription_id: int,
        transcript: str,
        segments: List[Dict],
        language: str,
        avg_confidence: float
    ) -> Transcription:
        """
        Update transcription with results from Whisper.
        Creates chunks, generates embeddings.
        """
        pass

    @staticmethod
    async def get_user_transcriptions(
        db: AsyncSession,
        user_id: str,
        filters: Optional[Dict] = None
    ) -> List[Transcription]:
        """
        List user's transcriptions with optional filtering.
        """
        pass

    @staticmethod
    async def assign_topics(
        db: AsyncSession,
        transcription_id: int,
        topic_ids: List[int],
        user_id: str
    ) -> List[TranscriptionTopic]:
        """
        Assign topics to transcription (user-initiated).
        """
        pass

    @staticmethod
    async def add_to_collection(
        db: AsyncSession,
        transcription_id: int,
        collection_id: int,
        user_id: str,
        position: Optional[int] = None
    ) -> TranscriptionCollection:
        """
        Add transcription to collection.
        """
        pass
```

---

## 4. Workflow Changes

### 4.1 DownloadAudioWorkflow

**Location**: `app/workflows/download/workflow.py`

**Purpose**: Download audio from URL and create AudioFile record.

**Input**:
```python
@dataclass
class DownloadAudioInput:
    user_id: str
    source_url: str
    job_id: int  # For status tracking
```

**Activities**:

1. **ValidateUrlActivity**: Check URL is supported by yt-dlp
2. **DownloadAudioActivity**: Download using yt-dlp to temp folder
3. **CalculateChecksumActivity**: Calculate SHA256 hash
4. **CheckDuplicateActivity**: Query database for existing file
5. **MoveFileActivity**: Move to user folder (if not duplicate)
6. **CreateAudioFileActivity**: Create AudioFile record
7. **UpdateJobActivity**: Mark job as completed

**Output**:
```python
@dataclass
class DownloadAudioOutput:
    audio_file_id: int
    checksum: str
    file_path: str
    is_duplicate: bool
```

**Error Handling**:
- Invalid URL → mark job as failed
- Download error → retry 3 times, then fail
- Disk full → fail with clear error message

### 4.2 TranscribeWorkflow (Updated)

**Location**: `app/workflows/transcribe/workflow.py`

**Changes**:
- **Before**: Accepted file upload, created Job record
- **After**: Accepts `audio_file_id`, creates Transcription record

**Input**:
```python
@dataclass
class TranscribeWorkflowInput:
    audio_file_id: int  # Changed from file upload
    user_id: str
    job_id: int
    model: str = "whisper-large-v3"
```

**Activities** (updated):

1. **LoadAudioFileActivity**: Fetch AudioFile record from database
2. **CreateTranscriptionActivity**: Create Transcription record (status='pending')
3. **TranscribeActivity**: Run Whisper on audio file
4. **GenerateChunksActivity**: Split transcript into chunks
5. **GenerateEmbeddingsActivity**: Create vector embeddings for chunks
6. **SaveTranscriptionActivity**: Save results to Transcription record
7. **UpdateJobActivity**: Mark job as completed

**Output**:
```python
@dataclass
class TranscribeWorkflowOutput:
    transcription_id: int
    transcript: str
    language: str
    chunk_count: int
```

---

## 5. API Endpoints

### 5.1 Audio File Management

#### POST /audio/upload
Upload local audio file.

**Request**:
```
Content-Type: multipart/form-data

file: <audio file>
```

**Response**:
```json
{
  "audio_file_id": 123,
  "filename": "recording.mp3",
  "file_size": 5242880,
  "duration": 300.5,
  "checksum": "a1b2c3...",
  "is_duplicate": false,
  "created_at": "2025-10-19T12:00:00Z"
}
```

**Business Logic**:
1. Calculate checksum
2. Check for duplicate (user_id + checksum)
3. If duplicate, return existing record
4. If new, save to user folder, create AudioFile record

#### POST /audio/download
Download audio from URL (triggers DownloadAudioWorkflow).

**Request**:
```json
{
  "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Response**:
```json
{
  "job_id": 456,
  "status": "pending",
  "message": "Download started. Check job status for progress."
}
```

**Business Logic**:
1. Validate URL (yt-dlp support check)
2. Create Job record (job_type='download')
3. Start DownloadAudioWorkflow
4. Return job_id for status tracking

#### GET /audio
List user's audio files with pagination and filtering.

**Query Parameters**:
- `source_type`: 'upload' | 'download' (optional)
- `limit`: max results (default: 50)
- `offset`: pagination offset (default: 0)

**Response**:
```json
{
  "total": 125,
  "limit": 50,
  "offset": 0,
  "audio_files": [
    {
      "id": 123,
      "filename": "recording.mp3",
      "file_size": 5242880,
      "duration": 300.5,
      "source_type": "upload",
      "source_url": null,
      "created_at": "2025-10-19T12:00:00Z",
      "transcription_count": 1
    },
    ...
  ]
}
```

#### GET /audio/{audio_file_id}
Get single audio file details.

**Response**:
```json
{
  "id": 123,
  "filename": "recording.mp3",
  "file_path": "uploads/user_30/2025/10/a1b2c3_recording.mp3",
  "file_size": 5242880,
  "mime_type": "audio/mpeg",
  "duration": 300.5,
  "checksum": "a1b2c3...",
  "source_type": "upload",
  "source_url": null,
  "source_platform": null,
  "created_at": "2025-10-19T12:00:00Z",
  "transcriptions": [
    {
      "id": 789,
      "status": "completed",
      "language": "en",
      "created_at": "2025-10-19T12:05:00Z"
    }
  ]
}
```

#### DELETE /audio/{audio_file_id}
Delete audio file (and cascade delete transcriptions).

**Response**:
```json
{
  "message": "Audio file deleted successfully",
  "deleted_transcriptions": 2
}
```

### 5.2 Transcription Management

#### POST /audio/{audio_file_id}/transcribe
Manually trigger transcription for an audio file.

**Request** (optional body):
```json
{
  "model": "whisper-large-v3",
  "language": "en"  // Optional: force language
}
```

**Response**:
```json
{
  "job_id": 789,
  "transcription_id": 456,
  "status": "pending",
  "message": "Transcription started. Check job status for progress."
}
```

**Business Logic**:
1. Verify user owns audio file
2. Create Transcription record (status='pending')
3. Create Job record (job_type='transcription', audio_file_id=X)
4. Start TranscribeWorkflow
5. Return job_id and transcription_id

#### GET /transcriptions
List user's transcriptions with filtering.

**Query Parameters**:
- `audio_file_id`: filter by audio file (optional)
- `status`: 'pending' | 'processing' | 'completed' | 'failed' (optional)
- `collection_id`: filter by collection (optional)
- `topic_id`: filter by topic (optional)
- `limit`: max results (default: 50)
- `offset`: pagination offset (default: 0)

**Response**:
```json
{
  "total": 87,
  "limit": 50,
  "offset": 0,
  "transcriptions": [
    {
      "id": 456,
      "audio_file": {
        "id": 123,
        "filename": "recording.mp3"
      },
      "status": "completed",
      "language": "en",
      "avg_confidence": 0.92,
      "created_at": "2025-10-19T12:05:00Z",
      "topics": [
        {"id": 5, "name": "Bible Study"}
      ],
      "collections": [
        {"id": 10, "name": "Sunday Sermons", "position": 3}
      ]
    },
    ...
  ]
}
```

#### GET /transcriptions/{transcription_id}
Get single transcription with full details.

**Response**:
```json
{
  "id": 456,
  "audio_file": {
    "id": 123,
    "filename": "recording.mp3",
    "duration": 300.5,
    "source_type": "upload"
  },
  "transcript": "Full transcript text...",
  "language": "en",
  "model_name": "whisper-large-v3",
  "avg_confidence": 0.92,
  "status": "completed",
  "created_at": "2025-10-19T12:05:00Z",
  "chunks": [
    {
      "chunk_index": 0,
      "text": "First chunk text...",
      "start_time": 0.0,
      "end_time": 30.0,
      "confidence": 0.95
    },
    ...
  ],
  "topics": [...],
  "collections": [...]
}
```

#### GET /transcriptions/{transcription_id}/download
Download transcript in various formats (SRT, VTT, TXT, JSON).

**Query Parameters**:
- `format`: 'srt' | 'vtt' | 'txt' | 'json' (default: 'srt')

**Response**: File download

#### DELETE /transcriptions/{transcription_id}
Delete transcription (keeps audio file).

**Response**:
```json
{
  "message": "Transcription deleted successfully"
}
```

### 5.3 Updated Upload Endpoint

#### POST /upload (Updated)

**Old Behavior**:
- Accept file upload
- Create Job record immediately
- Start TranscribeWorkflow

**New Behavior**:
- Accept file upload
- Create AudioFile record (with deduplication)
- Return audio_file_id
- User calls `/audio/{id}/transcribe` separately

**Request**:
```
Content-Type: multipart/form-data

file: <audio file>
```

**Response**:
```json
{
  "audio_file_id": 123,
  "filename": "recording.mp3",
  "file_size": 5242880,
  "duration": 300.5,
  "is_duplicate": false,
  "message": "Audio file uploaded. Call POST /audio/{id}/transcribe to start transcription."
}
```

---

## 6. Implementation Phases

### Phase 1: Database Schema (Week 1)

**Tasks**:
1. Create Alembic migration for new tables
   - `audio_files`
   - `transcriptions`
   - `transcription_chunks`
   - `transcription_topics`
   - `transcription_collections`
2. Update `jobs` table schema (add job_type, audio_file_id, source_url)
3. Run migration on development database
4. Verify all foreign keys and indexes created correctly

**Deliverables**:
- Migration file: `alembic/versions/XXXXXX_media_sourcing_refactor.py`
- Updated `app/data/models.py` with new SQLAlchemy models

**Testing**:
- Unit tests for model relationships
- Cascade delete tests
- Unique constraint tests

### Phase 2: Service Layer (Week 2)

**Tasks**:
1. Implement `AudioFileService`
   - File upload handling
   - Checksum calculation
   - Deduplication logic
   - User folder creation
   - Metadata extraction (ffprobe integration)
2. Implement `DownloadService`
   - yt-dlp integration
   - Platform detection
   - URL validation
   - Audio extraction configuration
3. Update `TranscriptionService`
   - Create/update transcription records
   - Chunk management
   - Topic/collection assignment

**Deliverables**:
- `app/services/audio_file_service.py`
- `app/services/download_service.py`
- Updated `app/services/transcription_service.py`

**Testing**:
- Service unit tests with mocked database
- Deduplication tests
- yt-dlp integration tests (use test fixtures)

### Phase 3: Workflows (Week 3)

**Tasks**:
1. Create `DownloadAudioWorkflow`
   - Implement all activities (validate, download, checksum, etc.)
   - Error handling and retries
   - Job status updates
2. Update `TranscribeWorkflow`
   - Change input from file upload to audio_file_id
   - Update activities to work with AudioFile records
   - Update result handling to create Transcription records

**Deliverables**:
- `app/workflows/download/workflow.py`
- `app/workflows/download/activities.py`
- Updated `app/workflows/transcribe/workflow.py`
- Updated `app/workflows/transcribe/activities.py`

**Testing**:
- Workflow integration tests
- Activity unit tests
- Error scenario tests (network failures, invalid URLs)

### Phase 4: API Endpoints (Week 4)

**Tasks**:
1. Create audio file router
   - POST /audio/upload
   - POST /audio/download
   - GET /audio
   - GET /audio/{id}
   - DELETE /audio/{id}
2. Create transcription router
   - POST /audio/{id}/transcribe
   - GET /transcriptions
   - GET /transcriptions/{id}
   - GET /transcriptions/{id}/download
   - DELETE /transcriptions/{id}
3. Update existing /upload endpoint (backward compatibility wrapper)
4. Update topic/collection assignment endpoints

**Deliverables**:
- `app/routers/audio_files.py`
- `app/routers/transcriptions.py`
- `app/schemas/audio_files.py`
- `app/schemas/transcriptions.py`
- Updated `main.py`

**Testing**:
- API integration tests (FastAPI TestClient)
- Authentication/authorization tests
- Pagination tests
- Error response tests

### Phase 5: Testing & Documentation (Week 5)

**Tasks**:
1. End-to-end testing
   - Upload → transcribe → download flow
   - URL download → transcribe flow
   - Deduplication scenarios
   - Topic/collection assignment
2. Update documentation
   - API.md with new endpoints
   - ARCHITECTURE.md with new diagrams
   - Update docker/verify scripts
3. Performance testing
   - Large file uploads
   - Concurrent downloads
   - Database query optimization

**Deliverables**:
- `tests/e2e/test_media_sourcing.py`
- Updated documentation
- Updated test scripts
- Performance benchmarks

**Testing**:
- Load testing (concurrent uploads/downloads)
- Stress testing (large files, many users)
- Deduplication performance tests

### Phase 6: Deployment (Week 6)

**Tasks**:
1. Update deployment configurations
   - Docker compose changes (yt-dlp installation)
   - Kubernetes manifests
   - Environment variables
2. Data migration strategy (if needed)
   - Clean start means no migration
   - But document process if users want to preserve data
3. Production deployment
   - Database backup
   - Run migration
   - Deploy new code
   - Monitor error rates

**Deliverables**:
- Updated docker/docker-compose.yml
- Updated deployment manifests
- Deployment runbook
- Rollback plan

**Testing**:
- Staging environment deployment
- Production smoke tests
- Monitoring and alerting setup

---

## 7. Testing Strategy

### 7.1 Unit Tests

**Coverage Areas**:
- AudioFileService: checksum calculation, deduplication, path generation
- DownloadService: URL validation, platform detection, yt-dlp options
- TranscriptionService: record creation, status updates, linking
- Models: relationships, cascade deletes, unique constraints

**Tools**:
- pytest
- pytest-asyncio
- SQLAlchemy test session fixtures

### 7.2 Integration Tests

**Coverage Areas**:
- API endpoints with database
- Workflow execution (mocked Temporal)
- File system operations
- yt-dlp integration (use test fixtures, not real downloads)

**Tools**:
- FastAPI TestClient
- pytest fixtures for database setup
- Mock yt-dlp responses

### 7.3 End-to-End Tests

**Scenarios**:
1. User uploads file → transcribes → downloads transcript
2. User provides YouTube URL → downloads → transcribes
3. User uploads same file twice → deduplication works
4. User assigns topics → filters by topic
5. User creates collection → adds transcriptions → reorders

**Tools**:
- pytest
- Real database (test instance)
- Real file system (temp directories)
- Mock yt-dlp for downloads

### 7.4 Performance Tests

**Benchmarks**:
- Upload 100MB file: < 10 seconds
- Calculate checksum 100MB file: < 5 seconds
- Deduplication query: < 100ms
- List 1000 audio files with pagination: < 500ms
- Concurrent uploads (10 users): no errors

**Tools**:
- pytest-benchmark
- Locust (for load testing)
- Database query profiling

---

## 8. Rollout Plan

### 8.1 Development Environment

**Timeline**: Week 1-5

1. Run migration on dev database
2. Test all new endpoints
3. Verify workflows execute correctly
4. Test with docker/verify scripts

### 8.2 Staging Environment

**Timeline**: Week 6

1. Deploy to staging
2. Run full test suite
3. Performance testing
4. User acceptance testing (if applicable)

### 8.3 Production Deployment

**Timeline**: Week 7

1. **Pre-deployment**:
   - Database backup
   - Feature flag setup (gradual rollout)
   - Monitoring dashboards ready

2. **Deployment**:
   - Apply database migration (downtime: ~5 minutes)
   - Deploy new application code
   - Verify health checks pass

3. **Post-deployment**:
   - Monitor error rates (target: < 0.1%)
   - Monitor API latency (target: p95 < 500ms)
   - Monitor disk usage (new folder structure)
   - User feedback collection

4. **Rollback Plan**:
   - If critical errors > 5% of requests
   - If database migration fails
   - Rollback: revert code, restore database backup

---

## 9. Security Considerations

### 9.1 File Upload Security

- **File Type Validation**: Only allow audio/video MIME types
- **File Size Limits**: Configurable max size (default: 500MB)
- **Virus Scanning**: Optional ClamAV integration
- **Path Traversal Prevention**: Sanitize filenames, use absolute paths

### 9.2 URL Download Security

- **URL Validation**: Whitelist supported domains (optional)
- **SSRF Prevention**: Block internal/private IP addresses
- **Rate Limiting**: Limit downloads per user (e.g., 10/hour)
- **Timeout**: Maximum download time (e.g., 10 minutes)

### 9.3 Access Control

- **User Isolation**: Users can only access their own audio files and transcriptions
- **Permission Checks**: All endpoints verify user ownership
- **Admin Overrides**: Admin users can access all resources (for moderation)

### 9.4 Data Privacy

- **Encryption at Rest**: Optional disk encryption for uploads folder
- **Encryption in Transit**: HTTPS for all API endpoints
- **Data Retention**: User-initiated deletion permanently removes files
- **Audit Logging**: Log all file uploads, downloads, deletions

---

## 10. Open Questions & Decisions

### 10.1 Resolved

✅ **Data Migration**: No migration, clean start
✅ **Workflow Separation**: Download and transcribe are separate workflows
✅ **yt-dlp Sources**: Support all sources (not just YouTube)
✅ **Metadata Storage**: Audio extraction only, no metadata
✅ **Storage Limits**: No limits, indefinite retention
✅ **Deduplication**: SHA256 checksum-based

### 10.2 To Be Decided

⏳ **File Size Limits**: What's the maximum file size for uploads? (Recommend: 500MB)
⏳ **Download Timeout**: Maximum time for yt-dlp downloads? (Recommend: 10 minutes)
⏳ **Rate Limiting**: How many downloads per user per hour? (Recommend: 10)
⏳ **Virus Scanning**: Integrate ClamAV for uploaded files? (Recommend: Yes for production)
⏳ **Audio Format Conversion**: Convert all uploads to MP3 for consistency? (Recommend: Yes)
⏳ **Concurrent Transcriptions**: Limit per user? (Recommend: 3 concurrent)
⏳ **Temporary File Cleanup**: How often to clean temp folder? (Recommend: Daily cron job)

---

## 11. Success Metrics

### 11.1 Technical Metrics

- **Database Migration**: Successfully applied with 0 errors
- **API Response Time**: p95 < 500ms for all endpoints
- **Error Rate**: < 0.1% of requests fail
- **Deduplication Rate**: > 90% of duplicate uploads detected
- **Download Success Rate**: > 95% of yt-dlp downloads succeed

### 11.2 User Metrics

- **Upload Flow Completion**: > 90% of uploads result in transcription
- **Download Flow Completion**: > 80% of downloads result in transcription
- **User Satisfaction**: Measured via feedback form (target: 4.5/5)

### 11.3 Performance Metrics

- **Disk Usage**: Deduplication saves > 30% disk space
- **Database Query Time**: All queries < 100ms (p95)
- **Concurrent Users**: Support 100+ concurrent uploads without errors

---

## 12. References

### 12.1 Related Documents

- [PHASE_1_DATABASE_AND_MODELS.md](./collections_and_topics/PHASE_1_DATABASE_AND_MODELS.md) - Original collections/topics schema
- [PHASE_2_API_ENDPOINTS.md](./collections_and_topics/PHASE_2_API_ENDPOINTS.md) - API endpoint patterns
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture

### 12.2 External Resources

- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)

---

## Appendix A: Example yt-dlp Usage

### A.1 Basic Download

```bash
yt-dlp \
  --extract-audio \
  --audio-format mp3 \
  --audio-quality 0 \
  --output "%(id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### A.2 Python Integration

```python
import yt_dlp

ydl_opts = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'audioquality': 0,
    'outtmpl': '/tmp/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=True)
    filename = ydl.prepare_filename(info)
    print(f"Downloaded: {filename}")
```

---

## Appendix B: Database Schema Diagram

```
┌─────────────┐
│   users     │
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────────┐
│  audio_files    │◄─────────┐
│                 │          │
│ - id            │          │
│ - user_id       │          │
│ - file_path     │          │
│ - checksum      │          │
│ - source_type   │          │
│ - source_url    │          │
└────────┬────────┘          │
         │                   │
         │ 1:N               │
         ▼                   │
┌──────────────────┐         │
│ transcriptions   │         │
│                  │         │
│ - id             │         │
│ - audio_file_id  │─────────┘
│ - user_id        │
│ - transcript     │
│ - status         │
└────────┬─────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────┐
│ transcription_chunks    │
│                         │
│ - id                    │
│ - transcription_id      │
│ - chunk_index           │
│ - text                  │
│ - embedding (vector)    │
└─────────────────────────┘

         │
         │ N:M
         ▼
┌──────────────────────────┐
│ transcription_topics     │
│                          │
│ - transcription_id       │
│ - topic_id               │
│ - ai_confidence          │
└──────────────────────────┘

         │
         │ N:M
         ▼
┌──────────────────────────┐
│ transcription_collections│
│                          │
│ - transcription_id       │
│ - collection_id          │
│ - position               │
└──────────────────────────┘
```

---

## Appendix C: API Flow Diagrams

### C.1 Local Upload → Transcribe Flow

```
User                API               AudioFileService    TranscriptionService    TranscribeWorkflow
 │                   │                       │                    │                       │
 ├──POST /audio/upload──►                    │                    │                       │
 │                   ├──create_from_upload──►│                    │                       │
 │                   │                       ├──calculate_checksum│                       │
 │                   │                       ├──check_duplicate   │                       │
 │                   │                       ├──save_to_folder    │                       │
 │                   │                       ├──create_record     │                       │
 │                   │◄──audio_file─────────┤                    │                       │
 │◄──audio_file_id───┤                       │                    │                       │
 │                   │                       │                    │                       │
 ├──POST /audio/{id}/transcribe──►           │                    │                       │
 │                   ├──────────────────────────create_transcription►                     │
 │                   │                       │                    ├──start_workflow───────►
 │                   │◄──────────────────────────transcription_id─┤                       │
 │◄──job_id─────────┤                       │                    │                       │
```

### C.2 URL Download → Transcribe Flow

```
User                API               DownloadService     AudioFileService    TranscribeWorkflow
 │                   │                       │                    │                  │
 ├──POST /audio/download──►                  │                    │                  │
 │                   ├──validate_url────────►│                    │                  │
 │                   ├──start_workflow───────►                    │                  │
 │◄──job_id─────────┤                       │                    │                  │
 │                   │                       │                    │                  │
 │                   │   (DownloadAudioWorkflow)                  │                  │
 │                   │                       ├──download_audio───►│                  │
 │                   │                       ├──calculate_checksum│                  │
 │                   │                       ├──move_to_folder────┤                  │
 │                   │                       ├──create_record─────►                  │
 │                   │                       │                    │                  │
 ├──GET /jobs/{id}──►│                       │                    │                  │
 │◄──status: completed─┤                     │                    │                  │
 │                   │                       │                    │                  │
 ├──POST /audio/{id}/transcribe──►           │                    │                  │
 │                   ├──────────────────────────────────────────start_workflow──────►
 │◄──job_id─────────┤                       │                    │                  │
```

---

**End of Document**
