# Complete Ecosystem Architecture

## Overview
This document describes how MxWhisper, MxPodcaster, Bible MCP, and n8n work together as a unified content creation ecosystem within the Kubernetes infrastructure.

---

## Ecosystem Vision

### The Big Picture
```
┌─────────────────────────────────────────────────────────────┐
│         KNOWLEDGE INPUT & ORGANIZATION                       │
│  ┌─────────────┐         ┌─────────────┐                    │
│  │  MxWhisper  │         │  Bible MCP  │                    │
│  │ (Knowledge) │         │ (Scripture) │                    │
│  └──────┬──────┘         └──────┬──────┘                    │
│         │                       │                            │
│         └───────────┬───────────┘                            │
│                     │                                        │
└─────────────────────┼────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │     n8n Workflows      │
         │   (Orchestration)      │
         └────────────┬───────────┘
                      │
                      ▼
┌─────────────────────┼────────────────────────────────────────┐
│                     │                                        │
│         CONTENT CREATION & PUBLISHING                        │
│  ┌──────────────────▼─────────────────┐                     │
│  │        MxPodcaster System          │                     │
│  │  ┌────────────┐   ┌────────────┐  │                     │
│  │  │   Script   │   │   Voice    │  │                     │
│  │  │ Generation │──▶│ Synthesis  │  │                     │
│  │  └────────────┘   └──────┬─────┘  │                     │
│  │                          │         │                     │
│  │  ┌────────────┐   ┌──────▼─────┐  │                     │
│  │  │   Human    │◀──│   Video    │  │                     │
│  │  │   Review   │   │  Render    │  │                     │
│  │  └──────┬─────┘   └────────────┘  │                     │
│  │         │                          │                     │
│  │  ┌──────▼─────┐                    │                     │
│  │  │  Publish   │                    │                     │
│  │  │  (YouTube) │                    │                     │
│  │  └────────────┘                    │                     │
│  └────────────────────────────────────┘                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## System Boundaries

### MxWhisper: Knowledge Management System
**Owns**:
- Audio transcription
- Semantic chunking
- Vector embeddings
- Topic categorization
- Collection organization
- Knowledge base search

**Provides**:
- REST API for uploads, search, retrieval
- MCP server for AI-native knowledge access
- PostgreSQL database (separate DB)
- Vector search capabilities

**Consumes**:
- User audio uploads
- LLM APIs (for categorization)

---

### MxPodcaster: Content Creation System
**Owns**:
- Script generation
- Voice synthesis
- Video rendering
- Publishing workflows
- Human review process

**Provides**:
- MCP server for content creation tools
- Review web application
- Video renderer service
- Publishing automation

**Consumes**:
- MxWhisper knowledge base (via MCP)
- Bible MCP (for scripture)
- Chatterbox TTS (voice)
- YouTube API (publishing)
- n8n orchestration

---

### Bible MCP: Scripture Reference System
**Owns**:
- Bible passage retrieval
- Multiple translations (ESV, NIV, KJV, etc.)
- Verse parsing and formatting

**Provides**:
- MCP tools for scripture access
- REST API endpoints

**Consumes**:
- Bible API services (external)

---

### n8n: Workflow Orchestration Layer
**Owns**:
- Workflow definitions
- Scheduling and triggers
- Error handling and retries
- Human approval gates
- Service coordination

**Provides**:
- Visual workflow builder
- Webhook endpoints
- Scheduled executions
- Integration hub

**Consumes**:
- All MCP servers (HTTP mode)
- Chatterbox API
- Video renderer API
- Review app webhooks
- External APIs (YouTube, Slack, etc.)

---

## Integration Patterns

### Pattern 1: MCP Tool Chain
**Use Case**: AI agent orchestrates multiple systems

```
Claude Desktop / AI Agent
         │
         ├─ MCP Protocol (stdio)
         │
         ▼
┌────────────────────┐
│  User Query:       │
│  "Create video     │
│   about Romans 3"  │
└────────┬───────────┘
         │
         ├─ search_knowledge_base("Romans 3")
         │  └─► MxWhisper MCP
         │       └─► Returns: sermon transcripts
         │
         ├─ get_bible_passage("Romans 3:23-24", "ESV")
         │  └─► Bible MCP
         │       └─► Returns: verse text
         │
         ├─ generate_video_script(...)
         │  └─► MxPodcaster MCP
         │       └─► Returns: script
         │
         ├─ create_narration(...)
         │  └─► MxPodcaster MCP
         │       └─► Calls Chatterbox
         │            └─► Returns: audio URL
         │
         ├─ render_video(...)
         │  └─► MxPodcaster MCP
         │       └─► Calls renderer
         │            └─► Returns: video URL
         │
         └─ publish_to_youtube(...)
            └─► MxPodcaster MCP
                 └─► Returns: YouTube URL
```

---

### Pattern 2: n8n Workflow Automation
**Use Case**: Scheduled or triggered content creation

```
n8n Workflow: "Daily Devotional"
         │
         ├─ Schedule Trigger: 6:00 AM
         │
         ├─ HTTP Request: Bible MCP
         │  └─► get_passage(today's reading)
         │
         ├─ HTTP Request: MxWhisper MCP
         │  └─► search_knowledge_base(related topic)
         │
         ├─ HTTP Request: MxPodcaster MCP
         │  └─► generate_video_script(...)
         │
         ├─ Webhook: Wait for human approval
         │  └─► Review App sends approval
         │
         ├─ HTTP Request: MxPodcaster MCP
         │  └─► create_narration(...)
         │
         ├─ HTTP Request: Video Renderer
         │  └─► render_video(...)
         │
         ├─ Webhook: Wait for final approval
         │
         └─ HTTP Request: MxPodcaster MCP
            └─► publish_to_youtube(...)
```

---

### Pattern 3: Event-Driven Processing
**Use Case**: New sermon triggers video creation

```
User uploads sermon audio
         │
         ▼
MxWhisper API: /upload
         │
         ├─ Creates Job
         ├─ Starts Temporal workflow
         │   ├─ Transcribe
         │   ├─ Chunk
         │   ├─ Categorize
         │   └─ Complete
         │
         ├─ On completion: Fires webhook
         │
         ▼
n8n: Webhook trigger "sermon_completed"
         │
         ├─ Check job metadata
         │   └─ Is part of series? Get collection
         │
         ├─ HTTP Request: MxPodcaster MCP
         │   └─► generate_video_script(job_id, collection)
         │
         ├─ ... (continue pipeline)
         │
         └─ Publish to series playlist
```

---

## Service Communication Matrix

| From ↓ / To → | MxWhisper API | MxWhisper MCP | Bible MCP | MxPodcaster MCP | Chatterbox | Video Renderer | Review App | YouTube |
|---------------|---------------|---------------|-----------|-----------------|------------|----------------|------------|---------|
| **User** | Upload audio | - | - | - | - | - | Approve | - |
| **n8n** | - | Search, get jobs | Get passages | All tools | Direct API | Direct API | Webhook | Direct API |
| **Claude** | - | All tools | All tools | All tools | - | - | - | - |
| **MxPodcaster MCP** | - | Search | Get verses | - | TTS API | Render API | - | Publish API |
| **Review App** | - | - | - | - | - | - | - | - |

---

## Data Flow: Complete User Journey

### Scenario: Weekly Sermon to YouTube Video

```
┌──────────────────────────────────────────────────────────┐
│ PHASE 1: Knowledge Capture (MxWhisper)                   │
└──────────────────────────────────────────────────────────┘

Sunday Morning:
  User → MxWhisper Web UI → Upload sermon.mp3
         │
         ├─ API creates Job
         ├─ Temporal workflow starts
         │   ├─ Whisper transcription (15 min)
         │   ├─ Semantic chunking (2 min)
         │   ├─ Generate embeddings (5 min)
         │   └─ AI categorization
         │       ├─ Detected topics: "Sermons", "Romans"
         │       ├─ Detected series: "Romans Study Series"
         │       └─ Confidence: 0.94
         │
         └─ Job status: COMPLETED
             Webhook fired: sermon_completed


┌──────────────────────────────────────────────────────────┐
│ PHASE 2: Content Creation Trigger (n8n)                  │
└──────────────────────────────────────────────────────────┘

n8n receives webhook:
  {
    "event": "sermon_completed",
    "job_id": 123,
    "collection_id": 5,  // "Romans Study Series"
    "position": 3
  }

n8n Workflow: "Sermon Video Producer" activates


┌──────────────────────────────────────────────────────────┐
│ PHASE 3: Script Generation (MxPodcaster)                 │
└──────────────────────────────────────────────────────────┘

n8n → MxPodcaster MCP: generate_video_script()
      Input:
        - job_id: 123
        - collection_id: 5
        - style: "sermon"
        - duration: "8-10 minutes"

MxPodcaster:
  ├─ Calls MxWhisper MCP:
  │   ├─ get_job(123) → Get sermon details
  │   ├─ get_transcript(123) → Full text
  │   └─ get_collection(5) → Series context
  │
  ├─ Identifies key scripture: "Romans 3:23-24"
  ├─ Calls Bible MCP:
  │   └─ get_passage("Romans 3:23-24", "ESV")
  │
  ├─ Calls LLM (Claude):
  │   ├─ Input: Transcript + scripture + series context
  │   └─ Generates structured script:
  │       ├─ Introduction (30s)
  │       ├─ Scripture reading (45s)
  │       ├─ Teaching points (5 min)
  │       ├─ Application (2 min)
  │       └─ Conclusion (30s)
  │
  └─ Returns script + metadata

n8n receives:
  {
    "script": "...",
    "estimated_duration": 540,
    "bible_references": ["Romans 3:23-24"],
    "key_points": [...]
  }


┌──────────────────────────────────────────────────────────┐
│ PHASE 4: Human Review (Review App)                       │
└──────────────────────────────────────────────────────────┘

n8n → Review App: Create review request
      │
      ├─ Saves draft to database
      ├─ Sends Slack notification:
      │   "📝 New sermon video script ready"
      │   "Preview: https://review.app/scripts/123"
      │   "Series: Romans Study Series (Episode 3)"
      │
      └─ n8n PAUSES workflow, waits for webhook

Pastor:
  ├─ Opens review link
  ├─ Reads script
  ├─ Makes minor edit: "Change 'folks' to 'brothers and sisters'"
  ├─ Clicks "Approve"
  │
  └─ Review App fires webhook → n8n resumes


┌──────────────────────────────────────────────────────────┐
│ PHASE 5: Voice Synthesis (Chatterbox)                    │
└──────────────────────────────────────────────────────────┘

n8n → MxPodcaster MCP: create_narration()
      Input:
        - script_text: "..." (approved version)
        - voice_profile: "pastor_john"
        - emotion: "thoughtful"
        - exaggeration: 0.5

MxPodcaster:
  ├─ Loads voice profile: /voices/pastor_john.wav
  ├─ Splits script into sentences
  ├─ For each sentence:
  │   └─ POST chatterbox.ai-services:8003/tts
  │       {
  │         "text": "...",
  │         "audio_prompt_path": "/voices/pastor_john.wav",
  │         "exaggeration": 0.5
  │       }
  │
  ├─ Concatenates audio segments
  ├─ Normalizes audio levels
  ├─ Saves: /audio/sermon_123_narration.wav
  │
  └─ Returns:
      {
        "audio_url": "s3://audio/sermon_123_narration.wav",
        "duration": 542.3
      }

n8n → Review App: Audio preview
      └─ Pastor listens, approves


┌──────────────────────────────────────────────────────────┐
│ PHASE 6: Video Rendering (ffmpeg)                        │
└──────────────────────────────────────────────────────────┘

n8n → Video Renderer: POST /render
      Input:
        - template: "sermon"
        - audio_url: "s3://audio/sermon_123_narration.wav"
        - text_overlays:
            - Scripture ref: "Romans 3:23-24" (0-5s)
            - Key point 1: "All have sinned" (45-50s)
            - Key point 2: "Justified by grace" (120-125s)
        - background: "series_background.jpg"
        - subtitles: true

Video Renderer:
  ├─ Generates SRT subtitle file
  ├─ Loads template: templates/sermon/config.yaml
  ├─ ffmpeg command:
  │   ├─ Input: audio + background image
  │   ├─ Text overlays with timing
  │   ├─ Burn in subtitles
  │   ├─ Encode: H.264, 1080p, 30fps
  │   └─ Output: /videos/sermon_123.mp4
  │
  └─ Returns:
      {
        "job_id": "render_456",
        "video_url": "s3://videos/sermon_123.mp4",
        "duration": 542.3,
        "filesize_mb": 85.2
      }

n8n → Review App: Video preview
      └─ Pastor watches, approves


┌──────────────────────────────────────────────────────────┐
│ PHASE 7: Publishing (YouTube)                            │
└──────────────────────────────────────────────────────────┘

n8n → Review App: Final metadata confirmation
      Pastor:
        ├─ Title: "Romans 3: Justified by Grace"
        ├─ Description: Auto-generated from script
        ├─ Tags: ["Bible Study", "Romans", "Grace"]
        ├─ Playlist: "Romans Study Series"
        ├─ Publish: "Schedule for Wednesday 6 PM"
        └─ Approves

n8n → MxPodcaster MCP: publish_to_youtube()
      Input:
        - video_url: "s3://videos/sermon_123.mp4"
        - title: "..."
        - description: "..."
        - tags: [...]
        - playlist_id: "PLxxx"
        - scheduled_publish: "2025-10-22T18:00:00Z"

MxPodcaster:
  ├─ Downloads video from storage
  ├─ YouTube Data API v3:
  │   ├─ videos.insert (upload)
  │   ├─ Set metadata
  │   ├─ Add to playlist
  │   └─ Set publish time
  │
  └─ Returns:
      {
        "youtube_id": "dQw4w9WgXcQ",
        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "status": "scheduled",
        "scheduled_for": "2025-10-22T18:00:00Z"
      }


┌──────────────────────────────────────────────────────────┐
│ PHASE 8: Notifications & Cleanup                         │
└──────────────────────────────────────────────────────────┘

n8n:
  ├─ Send Slack notification:
  │   "✅ Sermon video published!"
  │   "Series: Romans Study Series (3/12)"
  │   "Scheduled: Wednesday 6 PM"
  │   "URL: https://youtube.com/watch?v=dQw4w9WgXcQ"
  │
  ├─ Update MxWhisper job metadata:
  │   └─ POST /jobs/123/metadata
  │       {
  │         "youtube_url": "...",
  │         "published": true
  │       }
  │
  ├─ Cleanup temp files (optional)
  │
  └─ END workflow
```

---

## Cross-System Data Model

### Job Lifecycle Across Systems

```
MxWhisper Job:
{
  "id": 123,
  "user_id": 42,
  "title": "Sunday Sermon - Romans 3",
  "status": "completed",
  "audio_url": "s3://uploads/sermon.mp3",
  "transcript_id": 456,
  "topics": [
    {"id": 2, "name": "Sermons", "confidence": 0.95},
    {"id": 5, "name": "Romans", "confidence": 0.92}
  ],
  "collections": [
    {"id": 5, "name": "Romans Study Series", "position": 3}
  ],
  "metadata": {
    "duration": 3600,
    "word_count": 5420,
    "created_at": "2025-10-19T10:00:00Z"
  }
}

MxPodcaster Content:
{
  "source_job_id": 123,  // References MxWhisper
  "script_id": 789,
  "script": {
    "text": "...",
    "sections": [...],
    "bible_references": ["Romans 3:23-24"],
    "estimated_duration": 540
  },
  "audio": {
    "url": "s3://audio/sermon_123_narration.wav",
    "duration": 542.3,
    "voice_profile": "pastor_john"
  },
  "video": {
    "url": "s3://videos/sermon_123.mp4",
    "template": "sermon",
    "duration": 542.3,
    "filesize_mb": 85.2
  },
  "publishing": {
    "youtube_id": "dQw4w9WgXcQ",
    "youtube_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "status": "scheduled",
    "scheduled_for": "2025-10-22T18:00:00Z",
    "playlist": "Romans Study Series"
  },
  "reviews": [
    {"stage": "script", "status": "approved", "reviewed_at": "..."},
    {"stage": "audio", "status": "approved", "reviewed_at": "..."},
    {"stage": "video", "status": "approved", "reviewed_at": "..."}
  ]
}
```

---

## Deployment Architecture (Kubernetes)

### Namespace: ai-services

```
Services:
├── mxwhisper-api (ClusterIP)
│   └─ Internal: mxwhisper-api.ai-services.svc.cluster.local:8000
│   └─ External: mxwhisper.mixwarecs-home.net (Ingress)
│
├── mxwhisper-mcp (ClusterIP)
│   └─ Internal: mxwhisper-mcp.ai-services.svc.cluster.local:3000
│   └─ External: mxwhisper-mcp.mixwarecs-home.net (Ingress)
│
├── bible-mcp (ClusterIP)
│   └─ Internal: bible-mcp.ai-services.svc.cluster.local:3000
│   └─ External: bible-mcp.mixwarecs-home.net (Ingress)
│
├── mxpodcaster-mcp (ClusterIP)
│   └─ Internal: mxpodcaster-mcp.ai-services.svc.cluster.local:3000
│   └─ External: mxpodcaster-mcp.mixwarecs-home.net (Ingress)
│
├── chatterbox (ClusterIP)
│   └─ Internal: chatterbox.ai-services.svc.cluster.local:8003
│   └─ External: chatterbox.mixwarecs-home.net (Ingress - optional)
│
├── video-renderer (ClusterIP)
│   └─ Internal: video-renderer.ai-services.svc.cluster.local:8080
│
├── review-app (ClusterIP)
│   └─ Internal: review-app.ai-services.svc.cluster.local:8000
│   └─ External: review.mixwarecs-home.net (Ingress)
│
└── n8n (ClusterIP)
    └─ Internal: n8n.ai-services.svc.cluster.local:5678
    └─ External: ai-workflows.mixwarecs-home.net (Ingress)

Shared Infrastructure (already deployed):
├── PostgreSQL (multiple databases)
│   ├─ mxwhisper
│   ├─ mxpodcaster
│   └─ n8n
├── Redis (multiple namespaces)
│   ├─ mxwhisper:*
│   └─ mxpodcaster:*
└── Temporal
    ├─ namespace: mxwhisper
    └─ namespace: mxpodcaster (optional)
```

---

## Configuration Management

### Shared Secrets (Kubernetes)

```yaml
# ai-services namespace secrets
mxwhisper-secrets:
  - postgres_password
  - jwt_secret
  - api_key
  - openai_api_key

mxpodcaster-secrets:
  - mxwhisper_api_key
  - bible_mcp_api_key
  - youtube_client_id
  - youtube_client_secret
  - youtube_refresh_token
  - slack_webhook_url
  - openai_api_key

chatterbox-secrets:
  - (none - uses GPU)

n8n-secrets:
  - encryption_key
  - webhook_secret
```

### Environment Configuration

```
MxWhisper MCP:
  MCP_TRANSPORT=http
  MCP_PORT=3000
  MXWHISPER_API_URL=http://mxwhisper-api:8000
  MXWHISPER_API_KEY=<from secret>

MxPodcaster MCP:
  MCP_TRANSPORT=http
  MCP_PORT=3000
  MXWHISPER_MCP_URL=http://mxwhisper-mcp:3000
  BIBLE_MCP_URL=http://bible-mcp:3000
  CHATTERBOX_URL=http://chatterbox:8003
  VIDEO_RENDERER_URL=http://video-renderer:8080
  YOUTUBE_API_CREDENTIALS=<from secret>

n8n:
  N8N_EDITOR_BASE_URL=http://ai-workflows.mixwarecs-home.net
  EXECUTIONS_MODE=queue  # For scalability
  WEBHOOK_URL=http://ai-workflows.mixwarecs-home.net
```

---

## Error Handling & Resilience

### Failure Scenarios

#### 1. MxWhisper Transcription Fails
```
n8n Workflow:
  ├─ Webhook: sermon_uploaded
  ├─ Wait for completion (polling)
  ├─ Check status
  │   └─ If FAILED:
  │       ├─ Send alert to Slack
  │       ├─ Retry upload (if transient error)
  │       └─ Abort content creation
```

#### 2. Script Generation Fails
```
n8n Workflow:
  ├─ Call generate_video_script()
  ├─ On error:
  │   ├─ Retry with different parameters
  │   ├─ If 3 failures:
  │       └─ Send alert, pause workflow
```

#### 3. Chatterbox TTS Unavailable
```
MxPodcaster MCP:
  ├─ Try Chatterbox API
  ├─ If timeout/error:
  │   ├─ Retry 3x with backoff
  │   ├─ If still failing:
  │       └─ Fallback to OpenAI TTS (lower quality)
```

#### 4. Video Rendering Fails
```
n8n Workflow:
  ├─ POST /render
  ├─ Poll status
  ├─ If render fails:
  │   ├─ Check error type
  │   ├─ If resource issue: Wait 5 min, retry
  │   ├─ If config issue: Alert admin
  │   └─ If 3 failures: Abort
```

#### 5. YouTube Publish Fails
```
MxPodcaster:
  ├─ Upload video to YouTube
  ├─ If quota exceeded:
  │   └─ Queue for next day
  ├─ If auth error:
  │   └─ Alert admin to refresh token
  ├─ If other error:
  │   └─ Retry 3x, then manual intervention
```

---

## Monitoring Strategy

### Key Metrics

#### MxWhisper
- Transcription job success rate
- Average processing time
- Queue depth
- Storage usage
- Search query latency

#### MxPodcaster
- Scripts generated per day
- Voice synthesis duration
- Video render time
- YouTube publish success rate
- Human review SLA (time to approval)

#### n8n
- Active workflows
- Workflow success rate
- Average execution time
- Failed executions (alerts)

#### System-Wide
- API request rates
- Error rates by service
- Resource utilization (CPU, memory, GPU)
- Storage capacity

### Alerting Rules

```
Critical:
- MxWhisper API down > 5 min
- Chatterbox GPU not available
- Video render failed 3x
- YouTube publish failed
- Storage >90% capacity

Warning:
- Transcription queue > 10 jobs
- Review pending > 24 hours
- API latency >2s (p99)
- Error rate >1%
```

---

## Security & Access Control

### Authentication Flow

```
User → Web UI → API (JWT)
AI Agent → MCP (stdio - local trust)
n8n → MCP (HTTP + API key)
n8n → External APIs (OAuth/API keys)
```

### Authorization Levels

```
User Roles:
├── Admin
│   ├─ Manage topics
│   ├─ View all jobs
│   └─ System configuration
│
├── Content Creator
│   ├─ Upload audio
│   ├─ Create collections
│   ├─ Review content
│   └─ Publish videos
│
└── Viewer
    ├─ Search knowledge base
    └─ View own content
```

### Data Privacy

```
User Content:
├─ Audio files: Encrypted at rest (Ceph)
├─ Transcripts: Database encryption
├─ API tokens: Kubernetes secrets
├─ YouTube credentials: OAuth refresh tokens
└─ No data sharing between users (isolation)
```

---

## Scalability Path

### Current State (MVP)
- MxWhisper: 2 API replicas, 3 workers
- MxPodcaster: 1 replica each
- Chatterbox: 1 GPU pod
- Video Renderer: 1 CPU-heavy pod
- n8n: 1 replica

### Growth Path

#### Phase 1: Horizontal Scaling (10x traffic)
```
MxWhisper:
  - API: 5 replicas (HPA)
  - Workers: 10 replicas (HPA)
  - Read replicas for PostgreSQL

MxPodcaster:
  - Chatterbox: 3 GPU pods
  - Video Renderer: 5 CPU pods
  - n8n: 3 workers (queue mode)
```

#### Phase 2: Multi-Region (100x traffic)
```
- Regional clusters
- Object storage (S3) for media
- CDN for video delivery
- Multi-region PostgreSQL
- Federated search
```

#### Phase 3: Multi-Tenant (1000x traffic)
```
- Namespace per customer
- Resource quotas
- Dedicated databases
- White-label deployments
```

---

## Future Enhancements

### MxWhisper Extensions
1. Real-time transcription (WebSocket streaming)
2. Multi-language support
3. Speaker diarization integration
4. Custom vocabulary training
5. Export to multiple formats (PDF, DOCX, SRT)

### MxPodcaster Extensions
1. Multi-platform publishing (TikTok, Instagram, Facebook)
2. AI thumbnail generation
3. Automated A/B testing (titles, thumbnails)
4. Multi-language video generation
5. Live streaming support
6. Interactive video elements (polls, chapters)

### Integration Extensions
1. Zapier integration
2. Make.com integration
3. Direct LLM plugin (ChatGPT, Claude)
4. Mobile apps (iOS, Android)
5. Browser extension
6. VS Code extension

---

## Cost Optimization

### Cloud Costs
```
LLM APIs:
├─ Categorization: ~$0.01/job
├─ Script generation: ~$0.05/script
└─ Estimated: $100-500/month

Voice Synthesis:
├─ Chatterbox: Free (self-hosted GPU)
└─ Fallback OpenAI TTS: ~$0.015/min

Storage:
├─ Ceph (owned): No recurring cost
├─ Backup: Minimal
└─ Bandwidth: Depends on usage

YouTube:
└─ Free (API quota: 10,000 units/day)
```

### Optimization Strategies
1. **Cache aggressively**: Topic lists, Bible verses, embeddings
2. **Batch operations**: Process multiple jobs together
3. **Lazy loading**: Only generate videos on-demand
4. **Compression**: Optimize audio/video encoding
5. **Quotas**: Rate limit per user to control costs

---

## Related Documents

- [MxWhisper Architecture](MXWHISPER_ARCHITECTURE.md)
- [MxPodcaster Architecture](MXPODCASTER_ARCHITECTURE.md)
- [n8n Workflow Patterns](N8N_WORKFLOW_PATTERNS.md) (next)
- [Phase 1-4 Implementation Plans](collections_and_topics/)

---

**Document Status**: Architecture Planning
**Last Updated**: 2025-10-19
**Version**: 1.0
