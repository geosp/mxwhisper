# MxWhisper API Reference

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [User Endpoints](#user-endpoints)
- [Admin Endpoints](#admin-endpoints)
- [WebSocket API](#websocket-api)
- [Error Responses](#error-responses)
- [Rate Limiting](#rate-limiting)

## Overview

MxWhisper provides a RESTful API with real-time WebSocket support for audio transcription and semantic search.

**Base URL:**
```
http://localhost:8000
```

**Content Type:**
```
application/json
```

**Authentication:**
- All endpoints (except WebSocket) require JWT authentication
- Include token in `Authorization` header: `Bearer <token>`

## Authentication

### JWT Token Requirements

MxWhisper uses JWT tokens issued by Authentik for authentication.

**Token Format:**
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Required JWT Claims:**
```json
{
  "sub": "user-id-123",              // User identifier
  "email": "user@example.com",       // User email
  "name": "John Doe",                // Display name
  "preferred_username": "johndoe",   // Username
  "groups": ["users", "admin"],      // User groups (optional)
  "iss": "https://auth.example.com", // Issuer
  "aud": "mxwhisper",                // Audience
  "exp": 1234567890                  // Expiration timestamp
}
```

**Authentication Flow:**

```mermaid
sequenceDiagram
    participant Client
    participant Authentik
    participant MxWhisper

    Client->>Authentik: POST /application/o/token/<br/>(username, password)
    Authentik-->>Client: access_token

    Client->>MxWhisper: GET /user/jobs<br/>Authorization: Bearer {token}
    MxWhisper->>Authentik: Fetch JWKS (public keys)
    Authentik-->>MxWhisper: Public keys
    MxWhisper->>MxWhisper: Verify JWT signature
    MxWhisper->>MxWhisper: Validate claims
    MxWhisper-->>Client: 200 OK (jobs list)
```

**Obtaining a Token:**

```bash
# Get token from Authentik
curl -X POST https://auth.example.com/application/o/token/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=mxwhisper" \
  -d "client_secret=your-client-secret" \
  -d "username=user@example.com" \
  -d "password=yourpassword"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "..."
}
```

## User Endpoints

### Upload Audio File

Upload an audio file for transcription.

**Endpoint:** `POST /upload`

**Authentication:** Required

**Content-Type:** `multipart/form-data`

**Request:**

```bash
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@audio.mp3"
```

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | Yes | Audio file (MP3, WAV, M4A, etc.) Max size: 1GB |

**Response:** `200 OK`

```json
{
  "job_id": 123,
  "message": "File uploaded and transcription started"
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `413 Payload Too Large` | File exceeds maximum size (1GB) |
| `422 Unprocessable Entity` | Invalid file format |

---

### Get Job Status

Retrieve the status and details of a transcription job.

**Endpoint:** `GET /job/{job_id}`

**Authentication:** Required

**Request:**

```bash
curl -X GET http://localhost:8000/job/123 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | integer | Job identifier |

**Response:** `200 OK`

```json
{
  "job_id": 123,
  "status": "completed",
  "filename": "audio.mp3",
  "created_at": "2025-10-18T10:30:00Z",
  "updated_at": "2025-10-18T10:35:00Z",
  "transcript": "This is the transcribed text..."
}
```

**Job Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting for worker |
| `processing` | Transcription in progress |
| `completed` | Transcription finished successfully |
| `failed` | Transcription failed |

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `404 Not Found` | Job not found |

---

### Download Transcript

Download the completed transcript in TXT or SRT format.

**Endpoint:** `GET /jobs/{job_id}/download`

**Authentication:** Required

**Request:**

```bash
# Download as plain text
curl -X GET "http://localhost:8000/jobs/123/download?format=txt" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Download as SRT (subtitles)
curl -X GET "http://localhost:8000/jobs/123/download?format=srt" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | integer | Job identifier |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `txt` | Output format: `txt` or `srt` |

**Response:** `200 OK`

**Plain Text (format=txt):**
```
This is the transcribed text from the audio file.
It contains the full transcript without timestamps.
```

**SRT Format (format=srt):**
```
1
00:00:00,000 --> 00:00:05,500
This is the first subtitle

2
00:00:05,500 --> 00:00:10,200
This is the second subtitle
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `404 Not Found` | Job not found or not completed |

---

### Get User's Jobs

Retrieve all transcription jobs for the authenticated user.

**Endpoint:** `GET /user/jobs`

**Authentication:** Required

**Request:**

```bash
curl -X GET http://localhost:8000/user/jobs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** `200 OK`

```json
[
  {
    "id": 123,
    "filename": "audio1.mp3",
    "status": "completed",
    "created_at": "2025-10-18T10:30:00Z",
    "updated_at": "2025-10-18T10:35:00Z"
  },
  {
    "id": 124,
    "filename": "audio2.mp3",
    "status": "processing",
    "created_at": "2025-10-18T11:00:00Z",
    "updated_at": "2025-10-18T11:02:00Z"
  }
]
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |

---

### Semantic Search

Search across transcripts using semantic similarity.

**Endpoint:** `POST /search`

**Authentication:** Required

**Request:**

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "biblical teachings about the Messiah",
    "limit": 10
  }'
```

**Request Body:**

```json
{
  "query": "biblical teachings about the Messiah",
  "limit": 10
}
```

**Request Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search query (semantic, not keyword-based) |
| `limit` | integer | No | 10 | Maximum number of results to return |

**Response:** `200 OK`

```json
{
  "query": "biblical teachings about the Messiah",
  "results": [
    {
      "chunk_id": 45,
      "job_id": 123,
      "chunk_index": 2,
      "filename": "sermon.mp3",
      "matched_text": "The Bible also calls Him the Christ, the Greek word for Messiah, which means God's anointed one. He is the promised deliverer who brings salvation.",
      "topic_summary": "Discussion of Christ as the Messiah and His role as God's anointed deliverer",
      "keywords": ["Christ", "Messiah", "anointed", "salvation", "deliverer"],
      "timestamp": {
        "start": 145.5,
        "end": 178.2
      },
      "similarity": 0.89,
      "created_at": "2025-10-18T10:35:00Z"
    },
    {
      "chunk_id": 67,
      "job_id": 125,
      "chunk_index": 5,
      "filename": "bible_study.mp3",
      "matched_text": "The prophets foretold of the coming Messiah who would redeem God's people. Isaiah spoke of the suffering servant who would bear our iniquities.",
      "topic_summary": "Prophetic teachings about the coming Messiah and redemption",
      "keywords": ["Messiah", "prophets", "Isaiah", "redemption", "suffering servant"],
      "timestamp": {
        "start": 320.1,
        "end": 355.8
      },
      "similarity": 0.85,
      "created_at": "2025-10-17T15:20:00Z"
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `chunk_id` | integer | Unique chunk identifier |
| `job_id` | integer | Job that contains this chunk |
| `chunk_index` | integer | Position of chunk within the job |
| `filename` | string | Original audio filename |
| `matched_text` | string | Full text of the matching chunk |
| `topic_summary` | string | LLM-generated summary of chunk's topic |
| `keywords` | array[string] | Extracted keywords for the chunk |
| `timestamp.start` | float | Start time in audio (seconds) |
| `timestamp.end` | float | End time in audio (seconds) |
| `similarity` | float | Semantic similarity score (0-1, higher is better) |
| `created_at` | datetime | When the job was created |

**Search Examples:**

| Query | Finds |
|-------|-------|
| `"biblical teachings"` | Scripture, gospel, Christ, holy texts |
| `"love and compassion"` | Mercy, kindness, caring, empathy |
| `"ancient scriptures"` | Biblical texts, holy writings, sacred books |
| `"spiritual leader"` | Pastor, minister, priest, rabbi |
| `"God's anointed"` | Messiah, Christ, chosen one |

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `422 Unprocessable Entity` | Invalid query format |

---

## Admin Endpoints

Admin endpoints require the user to have admin privileges (member of admin group in Authentik).

### Get All Jobs

Retrieve all transcription jobs across all users.

**Endpoint:** `GET /admin/jobs`

**Authentication:** Required (Admin only)

**Request:**

```bash
curl -X GET http://localhost:8000/admin/jobs \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Response:** `200 OK`

```json
[
  {
    "id": 123,
    "filename": "audio1.mp3",
    "status": "completed",
    "user_id": "user-id-123",
    "created_at": "2025-10-18T10:30:00Z",
    "updated_at": "2025-10-18T10:35:00Z"
  },
  {
    "id": 124,
    "filename": "audio2.mp3",
    "status": "processing",
    "user_id": "user-id-456",
    "created_at": "2025-10-18T11:00:00Z",
    "updated_at": "2025-10-18T11:02:00Z"
  }
]
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | User is not an admin |

---

### Get All Users

Retrieve all users and their roles.

**Endpoint:** `GET /admin/users`

**Authentication:** Required (Admin only)

**Request:**

```bash
curl -X GET http://localhost:8000/admin/users \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Response:** `200 OK`

```json
[
  {
    "id": "user-id-123",
    "email": "user@example.com",
    "name": "John Doe",
    "preferred_username": "johndoe",
    "role": "user",
    "created_at": "2025-10-15T09:00:00Z",
    "updated_at": "2025-10-15T09:00:00Z"
  },
  {
    "id": "admin-id-456",
    "email": "admin@example.com",
    "name": "Admin User",
    "preferred_username": "admin",
    "role": "admin",
    "created_at": "2025-10-14T08:00:00Z",
    "updated_at": "2025-10-14T08:00:00Z"
  }
]
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | User is not an admin |

---

### Create User

Create a new user in both Authentik and the local database.

**Endpoint:** `POST /admin/users`

**Authentication:** Required (Admin only)

**Request:**

```bash
curl -X POST http://localhost:8000/admin/users \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "name": "New User",
    "preferred_username": "newuser",
    "password": "SecurePassword123!",
    "role": "user"
  }'
```

**Request Body:**

```json
{
  "email": "newuser@example.com",
  "name": "New User",
  "preferred_username": "newuser",
  "password": "SecurePassword123!",
  "role": "user"
}
```

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | string | Yes | User's email address |
| `name` | string | Yes | User's display name |
| `preferred_username` | string | Yes | Username for login |
| `password` | string | Yes | User's password |
| `role` | string | No | User role: `user` or `admin` (default: `user`) |

**Response:** `200 OK`

```json
{
  "id": "new-user-id-789",
  "email": "newuser@example.com",
  "name": "New User",
  "preferred_username": "newuser",
  "role": "user",
  "created_at": "2025-10-18T12:00:00Z",
  "updated_at": "2025-10-18T12:00:00Z"
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `400 Bad Request` | Failed to create user (e.g., email already exists) |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | User is not an admin |
| `422 Unprocessable Entity` | Invalid request format |

---

### Update User

Update user information.

**Endpoint:** `PUT /admin/users/{user_id}`

**Authentication:** Required (Admin only)

**Request:**

```bash
curl -X PUT http://localhost:8000/admin/users/user-id-123 \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "role": "admin"
  }'
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | string | User identifier |

**Request Body:**

```json
{
  "email": "newemail@example.com",
  "name": "Updated Name",
  "preferred_username": "newusername",
  "role": "admin"
}
```

**Request Parameters (all optional):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `email` | string | New email address |
| `name` | string | New display name |
| `preferred_username` | string | New username |
| `role` | string | New role: `user` or `admin` |

**Response:** `200 OK`

```json
{
  "id": "user-id-123",
  "email": "newemail@example.com",
  "name": "Updated Name",
  "preferred_username": "newusername",
  "role": "admin",
  "updated_at": "2025-10-18T12:30:00Z"
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `400 Bad Request` | Failed to update user |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | User is not an admin |
| `404 Not Found` | User not found |

---

### Delete User

Delete a user from the system.

**Endpoint:** `DELETE /admin/users/{user_id}`

**Authentication:** Required (Admin only)

**Request:**

```bash
curl -X DELETE http://localhost:8000/admin/users/user-id-123 \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | string | User identifier |

**Response:** `200 OK`

```json
{
  "message": "User user-id-123 deleted successfully"
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| `400 Bad Request` | Failed to delete user |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | User is not an admin |
| `404 Not Found` | User not found |

---

## WebSocket API

### Real-time Job Updates

Receive real-time status updates for a transcription job.

**Endpoint:** `WS /ws/jobs/{job_id}`

**Authentication:** Not required (WebSocket connections are not authenticated)

**Connection:**

```javascript
// JavaScript example
const jobId = 123;
const ws = new WebSocket(`ws://localhost:8000/ws/jobs/${jobId}`);

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Job update:', update);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket disconnected');
};
```

**Message Format:**

```json
{
  "job_id": 123,
  "status": "processing",
  "progress": 60,
  "message": "Transcription complete"
}
```

**Message Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | integer | Job identifier |
| `status` | string | Current status: `pending`, `processing`, `completed`, `failed` |
| `progress` | integer | Progress percentage (0-100), optional |
| `message` | string | Human-readable status message, optional |
| `error` | string | Error message if status is `failed`, optional |

**Status Updates:**

| Progress | Status | Message |
|----------|--------|---------|
| 0% | `processing` | Processing started |
| 60% | `processing` | Transcription complete |
| 80% | `processing` | Chunking complete |
| 100% | `completed` | Job completed successfully |
| - | `failed` | Error message in `error` field |

**Example Flow:**

```json
// 1. Job created
{"job_id": 123, "status": "pending"}

// 2. Processing started
{"job_id": 123, "status": "processing", "progress": 0, "message": "Processing started"}

// 3. Transcription done
{"job_id": 123, "status": "processing", "progress": 60, "message": "Transcription complete"}

// 4. Chunking done
{"job_id": 123, "status": "processing", "progress": 80, "message": "Chunking complete"}

// 5. Completed
{"job_id": 123, "status": "completed", "progress": 100, "message": "Job completed successfully"}
```

**Python Example:**

```python
import websockets
import asyncio
import json

async def listen_for_updates(job_id):
    uri = f"ws://localhost:8000/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            update = json.loads(message)
            print(f"Status: {update['status']}")
            if update.get('progress'):
                print(f"Progress: {update['progress']}%")
            if update['status'] in ['completed', 'failed']:
                break

asyncio.run(listen_for_updates(123))
```

---

## Error Responses

### Standard Error Format

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| `200 OK` | Request successful | - |
| `400 Bad Request` | Invalid request | Malformed JSON, validation errors |
| `401 Unauthorized` | Authentication required | Missing or invalid JWT token |
| `403 Forbidden` | Permission denied | User lacks required role (e.g., admin) |
| `404 Not Found` | Resource not found | Job ID doesn't exist, user not found |
| `413 Payload Too Large` | File too large | Audio file exceeds 1GB limit |
| `422 Unprocessable Entity` | Validation error | Invalid file type, missing required fields |
| `500 Internal Server Error` | Server error | Database error, service unavailable |

### Example Error Responses

**401 Unauthorized:**
```json
{
  "detail": "Invalid user token"
}
```

**403 Forbidden:**
```json
{
  "detail": "Admin access required"
}
```

**404 Not Found:**
```json
{
  "detail": "Job not found"
}
```

**413 Payload Too Large:**
```json
{
  "detail": "File too large (max 1073741824 bytes)"
}
```

---

## Rate Limiting

Currently, MxWhisper does not implement rate limiting. For production deployments, consider:

1. **API Gateway Rate Limiting**: Use Nginx, Kong, or cloud provider rate limiting
2. **Application-Level Limiting**: Implement using libraries like `slowapi`
3. **User-Based Limits**: Track upload counts per user

**Recommended Limits:**

| Endpoint | Suggested Limit |
|----------|----------------|
| `POST /upload` | 10 requests/hour per user |
| `POST /search` | 100 requests/minute per user |
| `GET /user/jobs` | 60 requests/minute per user |
| `GET /admin/*` | 100 requests/minute per admin |

---

## API Versioning

Current version: **v1** (implicit, no version in URL)

Future versions will use URL versioning:
- `/v1/upload`
- `/v2/upload`

---

## CORS Configuration

MxWhisper allows cross-origin requests with the following configuration:

```python
allow_origins = ["*"]  # Configure for production
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*", "Authorization"]
```

**Production Recommendation:**
```python
allow_origins = [
    "https://app.example.com",
    "https://admin.example.com"
]
```

---

## OpenAPI Documentation

Interactive API documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## Client Libraries

### Python Client Example

```python
import httpx
import asyncio

class MxWhisperClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    async def upload_file(self, file_path: str):
        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    f"{self.base_url}/upload",
                    headers=self.headers,
                    files={"file": f}
                )
                response.raise_for_status()
                return response.json()

    async def get_job_status(self, job_id: int):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/job/{job_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def search(self, query: str, limit: int = 10):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/search",
                headers=self.headers,
                json={"query": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json()

# Usage
async def main():
    client = MxWhisperClient(
        base_url="http://localhost:8000",
        token="your-jwt-token"
    )

    # Upload file
    result = await client.upload_file("audio.mp3")
    job_id = result["job_id"]

    # Check status
    status = await client.get_job_status(job_id)
    print(status)

    # Search
    results = await client.search("biblical teachings")
    print(results)

asyncio.run(main())
```

### JavaScript/TypeScript Client Example

```typescript
class MxWhisperClient {
  constructor(private baseUrl: string, private token: string) {}

  async uploadFile(file: File): Promise<{ job_id: number; message: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${this.baseUrl}/upload`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
  }

  async getJobStatus(jobId: number) {
    const response = await fetch(`${this.baseUrl}/job/${jobId}`, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to get job status: ${response.statusText}`);
    }

    return response.json();
  }

  async search(query: string, limit: number = 10) {
    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ query, limit })
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    return response.json();
  }

  connectWebSocket(jobId: number, onUpdate: (update: any) => void) {
    const ws = new WebSocket(`ws://${this.baseUrl.replace(/^https?:\/\//, '')}/ws/jobs/${jobId}`);

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      onUpdate(update);
    };

    return ws;
  }
}

// Usage
const client = new MxWhisperClient('http://localhost:8000', 'your-jwt-token');

// Upload and monitor
const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
const file = fileInput.files[0];

const { job_id } = await client.uploadFile(file);

// Connect WebSocket for real-time updates
const ws = client.connectWebSocket(job_id, (update) => {
  console.log(`Status: ${update.status}, Progress: ${update.progress}%`);
});
```

---

## Support

For API questions or issues:
- GitHub Issues: https://github.com/anthropics/mxwhisper/issues
- Documentation: See [README.md](../README.md)
