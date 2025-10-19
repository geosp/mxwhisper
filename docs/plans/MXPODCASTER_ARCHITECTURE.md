# MxPodcaster System Architecture

## Overview
MxPodcaster is a content creation system that transforms knowledge base content (from MxWhisper) into polished video/audio content for publishing on platforms like YouTube. It orchestrates script generation, voice synthesis, video rendering, and publishing workflows.

---

## System Purpose

### Primary Functions
1. **Script Generation** - Create video scripts from knowledge base content + Bible passages
2. **Voice Synthesis** - Generate natural-sounding narration (Chatterbox TTS)
3. **Video Rendering** - Combine audio, images, text overlays into videos (ffmpeg)
4. **Human Review** - Multi-stage approval workflow
5. **Publishing** - Automated upload to YouTube, social media
6. **Workflow Orchestration** - n8n-based pipeline automation

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   MXPODCASTER SYSTEM                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐      ┌──────────────┐      ┌────────────┐  │
│  │   Content  │      │   Voice &    │      │ Publishing │  │
│  │  Discovery │─────▶│    Video     │─────▶│  Pipeline  │  │
│  │            │      │  Production  │      │            │  │
│  └────────────┘      └──────────────┘      └────────────┘  │
│                                                              │
│  ┌────────────┐      ┌──────────────┐                       │
│  │    n8n     │◀─────│    Human     │                       │
│  │ Workflows  │      │    Review    │                       │
│  └────────────┘      └──────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. n8n Workflow Orchestrator
**Purpose**: Central brain coordinating all content creation steps

**Key Workflows**:
```
1. Daily Devotional Creator
   - Scheduled trigger (6 AM daily)
   - Get Bible verse
   - Search related MxWhisper content
   - Generate script
   - Create video
   - Publish

2. Sermon Video Producer
   - Webhook trigger (new sermon uploaded)
   - Wait for transcription
   - Generate video script
   - Human review checkpoints
   - Render and publish

3. Bible Study Series Creator
   - Manual trigger (user selects collection)
   - For each job in collection:
     - Generate episode script
     - Create video
     - Add to playlist
   - Publish series

4. Bulk Content Pipeline
   - Process multiple jobs
   - Queue-based execution
   - Batch rendering
   - Scheduled publishing
```

**Why n8n**:
- Visual workflow builder (easy to modify)
- Built-in integrations (YouTube, Slack, email)
- Error handling and retries
- Human approval nodes
- Scheduled triggers
- Webhook support

---

### 2. MCP Content Creator Server
**Purpose**: Provide MCP tools for content creation operations

**Features** (auto-discovered from `features/` directory):

#### Script Generation Feature
```
generate_video_script()
  Input:
    - bible_passage: "Romans 3:23-24"
    - knowledge_base_query: "grace and justification"
    - style: "teaching" | "devotional" | "sermon"
    - duration: "2-3 minutes"
    - mxwhisper_job_ids: [123, 456] (optional)

  Process:
    1. Search MxWhisper for related content
    2. Get Bible passage from Bible MCP
    3. Generate structured script (Claude/GPT)
       - Introduction
       - Scripture reading
       - Teaching points (from transcripts)
       - Application
       - Conclusion
    4. Estimate audio length
    5. Return script with metadata

  Output:
    {
      "script": "...",
      "sections": [...],
      "estimated_duration": 150,
      "sources": [job_ids],
      "bible_passage": {...}
    }
```

#### Voice Synthesis Feature
```
create_narration()
  Input:
    - script_text: "Full script text"
    - voice_profile: "pastor" | "default"
    - emotion: "thoughtful" | "excited" | "calm"
    - exaggeration: 0.6

  Process:
    1. Split script into sentences
    2. Call Chatterbox TTS API
       - Use voice cloning if profile specified
       - Apply emotion settings
    3. Concatenate audio segments
    4. Normalize audio levels
    5. Save to storage

  Output:
    {
      "audio_url": "s3://audio/narration123.wav",
      "duration": 145.5,
      "sample_rate": 24000,
      "format": "wav"
    }
```

#### Video Rendering Feature
```
render_video()
  Input:
    - audio_url: "s3://audio/narration123.wav"
    - template: "devotional" | "sermon" | "teaching"
    - background_image: "path/to/image.jpg"
    - text_overlays: [
        {text: "Romans 3:23-24", position: "top", duration: 5},
        {text: "Key Point", position: "bottom", duration: 3}
      ]
    - subtitles: true/false

  Process:
    1. Load template configuration
    2. Generate subtitle file (SRT) if requested
    3. Call ffmpeg renderer
       - Overlay image
       - Add audio track
       - Render text overlays
       - Burn in subtitles
    4. Encode video (H.264, 1080p)
    5. Save to storage

  Output:
    {
      "video_url": "s3://videos/video123.mp4",
      "duration": 145.5,
      "resolution": "1920x1080",
      "format": "mp4",
      "filesize_mb": 42.5
    }
```

#### Publishing Feature
```
publish_to_youtube()
  Input:
    - video_url: "s3://videos/video123.mp4"
    - title: "Understanding Grace - Romans 3"
    - description: "..."
    - tags: ["Bible Study", "Romans", "Grace"]
    - category: "Education"
    - playlist_id: "PLxxx" (optional)
    - scheduled_publish: "2025-10-20T10:00:00Z" (optional)

  Process:
    1. Download video from storage
    2. Upload to YouTube API
    3. Set metadata (title, description, tags)
    4. Add to playlist if specified
    5. Set publish time (immediate or scheduled)
    6. Return video URL

  Output:
    {
      "youtube_id": "dQw4w9WgXcQ",
      "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
      "status": "scheduled" | "published",
      "scheduled_for": "..."
    }
```

**Architecture Pattern**: mcp-weather core with automatic feature discovery

---

### 3. Chatterbox TTS Service
**Purpose**: High-quality voice synthesis with voice cloning

**Existing Implementation**: `/home/geo/develop/chatterbox-docker`

**Key Features**:
- Voice cloning from reference audio
- Emotion control (exaggeration, cfg_weight)
- GPU-accelerated inference (NVIDIA)
- REST API on port 8003
- Web UI on port 7861

**API Integration**:
```python
# n8n calls Chatterbox via HTTP
POST http://chatterbox.ai-services.svc.cluster.local:8003/tts
{
  "text": "For all have sinned and fall short of the glory of God",
  "audio_prompt_path": "/voices/pastor.wav",  # Voice cloning
  "exaggeration": 0.6,
  "cfg_weight": 0.4
}

Response:
{
  "audio_base64": "...",  # Or URL to saved file
  "duration": 4.2,
  "sample_rate": 24000
}
```

**Deployment**: Kubernetes pod with GPU affinity

---

### 4. Video Renderer Service
**Purpose**: ffmpeg-based video generation from audio + images

**Design**:
```
video-renderer/
├── api/                    # FastAPI service
│   ├── render.py          # Main rendering endpoint
│   └── templates.py       # Template manager
├── templates/             # Video templates
│   ├── devotional/
│   │   ├── config.yaml
│   │   └── assets/
│   ├── sermon/
│   └── teaching/
├── ffmpeg/                # ffmpeg wrapper
│   ├── compositor.py      # Image compositing
│   ├── subtitle.py        # SRT generation
│   └── encoder.py         # Video encoding
└── storage/               # Output storage
```

**Template Structure**:
```yaml
# templates/devotional/config.yaml
name: "Daily Devotional"
resolution: "1920x1080"
fps: 30
background:
  type: "image"  # or "video", "solid_color"
  path: "assets/cross-background.jpg"
  opacity: 0.8
text_overlays:
  - id: "scripture_ref"
    position: "top_center"
    font: "Arial Bold"
    size: 48
    color: "#FFFFFF"
    shadow: true
  - id: "key_point"
    position: "bottom_third"
    font: "Arial"
    size: 36
    color: "#FFDD00"
subtitle_style:
  font: "Arial"
  size: 32
  position: "bottom"
  background: "rgba(0,0,0,0.7)"
audio:
  normalize: true
  fade_in: 1.0
  fade_out: 1.5
encoding:
  codec: "libx264"
  preset: "medium"
  crf: 23
  audio_codec: "aac"
  audio_bitrate: "192k"
```

**API Endpoint**:
```python
POST /render
{
  "template": "devotional",
  "audio_url": "s3://audio/narration.wav",
  "text_overlays": [
    {"id": "scripture_ref", "text": "Romans 3:23-24", "start": 0, "end": 5},
    {"id": "key_point", "text": "We are justified by grace", "start": 30, "end": 35}
  ],
  "subtitles": true,
  "output_name": "romans-3-devotional"
}

Response:
{
  "job_id": "render_123",
  "status": "rendering",
  "estimated_time": 120
}

GET /render/{job_id}
{
  "status": "completed",
  "video_url": "s3://videos/romans-3-devotional.mp4",
  "duration": 145.5,
  "filesize_mb": 42.5
}
```

---

### 5. Review App (Human-in-the-Loop)
**Purpose**: Multi-stage approval interface for content quality

**Review Stages**:
```
1. Script Review
   - Preview generated script
   - Edit inline (optional)
   - Approve / Request Changes

2. Audio Review
   - Listen to narration
   - Check voice quality, pacing
   - Approve / Regenerate

3. Video Review
   - Watch preview video
   - Check visuals, timing
   - Approve / Request Changes

4. Publishing Review
   - Final metadata check
   - Confirm publish time
   - Approve / Schedule
```

**Interface**:
```
review-app/
├── web/                   # React frontend
│   ├── components/
│   │   ├── ScriptReview.tsx
│   │   ├── AudioPlayer.tsx
│   │   ├── VideoPreview.tsx
│   │   └── PublishForm.tsx
│   └── api/
│       └── client.ts      # API client
├── api/                   # FastAPI backend
│   ├── reviews.py         # Review CRUD
│   ├── webhooks.py        # n8n webhook handlers
│   └── notifications.py   # Slack/email alerts
└── db/
    └── models.py          # Review state tracking
```

**n8n Integration**:
```javascript
// n8n workflow node: "Wait for Script Approval"
1. Create review record in database
2. Send Slack notification with preview link
3. Pause workflow, wait for webhook
4. On webhook receive:
   - If approved: Continue
   - If changes requested: Loop back to script generation
```

**Webhook Endpoints**:
```
POST /webhooks/approve-script/{review_id}
POST /webhooks/reject-script/{review_id}
POST /webhooks/approve-audio/{review_id}
POST /webhooks/approve-video/{review_id}
POST /webhooks/approve-publish/{review_id}
```

---

## Data Flow: Complete Content Creation Pipeline

### Example: Daily Devotional Workflow

```
[n8n: Schedule Trigger - 6:00 AM Daily]
  ↓
[n8n: Get Today's Bible Verse]
  - Date → Bible reading plan
  - Returns: "Romans 3:23-24"
  ↓
[n8n: HTTP Request to MxWhisper MCP]
  - Tool: search_knowledge_base()
  - Query: "Romans 3 grace justification"
  - Returns: 3 related sermon transcripts
  ↓
[n8n: HTTP Request to MxPodcaster MCP]
  - Tool: generate_video_script()
  - Input: Bible verse + sermon IDs
  - Returns: 2-minute devotional script
  ↓
[Review App: Script Review]
  - Save draft script
  - Send Slack notification
  - PAUSE workflow
  ↓
[Human: Reviews Script]
  - Opens preview link
  - Makes minor edits
  - Clicks "Approve"
  - Webhook fired → n8n resumes
  ↓
[n8n: HTTP Request to MxPodcaster MCP]
  - Tool: create_narration()
  - Input: Approved script + voice profile
  - Returns: Audio URL
  ↓
[Review App: Audio Review]
  - Preview audio player
  - PAUSE workflow
  ↓
[Human: Approves Audio]
  - Webhook fired
  ↓
[n8n: HTTP Request to Video Renderer]
  - Template: "devotional"
  - Audio URL + text overlays
  - Returns: Video job ID
  ↓
[n8n: Wait for Render Complete]
  - Poll /render/{job_id} every 10s
  - Wait for status: "completed"
  ↓
[Review App: Video Review]
  - Embedded video player
  - PAUSE workflow
  ↓
[Human: Approves Video]
  - Confirms metadata
  - Sets publish time: "Today 10:00 AM"
  - Webhook fired
  ↓
[n8n: HTTP Request to MxPodcaster MCP]
  - Tool: publish_to_youtube()
  - Video URL + metadata + schedule
  - Returns: YouTube URL
  ↓
[n8n: Send Success Notification]
  - Slack: "✅ Daily devotional scheduled"
  - Link to YouTube video
  ↓
[END]
```

---

## Integration Architecture

### Service Communication (Kubernetes Internal)

```
┌────────────────────────────────────────────────────────┐
│              Kubernetes: ai-services Namespace         │
│                                                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│  │   n8n    │──▶│ MxWhisper│──▶│  Bible   │          │
│  │          │   │   MCP    │   │   MCP    │          │
│  └────┬─────┘   └──────────┘   └──────────┘          │
│       │                                                │
│       ├──────────────────────┐                        │
│       │                      │                        │
│  ┌────▼─────┐          ┌─────▼────┐                  │
│  │MxPodcaster│         │Chatterbox│                  │
│  │   MCP    │          │   TTS    │                  │
│  └────┬─────┘          └──────────┘                  │
│       │                                                │
│  ┌────▼─────┐          ┌──────────┐                  │
│  │  Video   │          │  Review  │                  │
│  │ Renderer │          │   App    │                  │
│  └──────────┘          └──────────┘                  │
│                                                        │
└────────────────────────────────────────────────────────┘

Service DNS Names:
- n8n: n8n.ai-services.svc.cluster.local:5678
- MxWhisper MCP: mxwhisper-mcp.ai-services.svc.cluster.local:3000
- Bible MCP: bible-mcp.ai-services.svc.cluster.local:3000
- MxPodcaster MCP: mxpodcaster-mcp.ai-services.svc.cluster.local:3000
- Chatterbox: chatterbox.ai-services.svc.cluster.local:8003
- Video Renderer: video-renderer.ai-services.svc.cluster.local:8080
- Review App: review-app.ai-services.svc.cluster.local:8000
```

---

## Storage Architecture

### Shared Storage (Ceph RBD)

```
PersistentVolumeClaims:
├── mxpodcaster-scripts (10Gi)
│   └── Generated scripts, drafts
│
├── mxpodcaster-audio (50Gi)
│   ├── narrations/
│   ├── voice_profiles/
│   └── temp/
│
├── mxpodcaster-videos (200Gi)
│   ├── rendered/
│   ├── published/
│   └── temp/
│
├── chatterbox-models (30Gi)
│   └── TTS model cache
│
└── video-templates (5Gi)
    └── Template assets
```

### Object Storage (Optional: S3-Compatible)

```
Buckets:
├── mxpodcaster-assets/
│   ├── backgrounds/
│   ├── overlays/
│   └── fonts/
│
├── mxpodcaster-output/
│   ├── audio/
│   ├── video/
│   └── thumbnails/
│
└── mxpodcaster-published/
    └── Archive of published content
```

---

## Workflow Patterns

### Pattern 1: Sequential with Reviews
```
Generate → Review → Approve → Next Step
(Script)   (Human)  (Continue) (Audio)
```

### Pattern 2: Parallel Processing
```
Generate Scripts (Batch)
     ↓
  Split Array
     ↓
┌────┼────┐
│    │    │
v    v    v
Audio1 Audio2 Audio3 (Parallel)
│    │    │
└────┼────┘
     ↓
   Merge
```

### Pattern 3: Conditional Logic
```
Check Collection Type
     ├─ "Series" → Add to Playlist
     ├─ "Standalone" → Publish Individual
     └─ "Draft" → Skip Publishing
```

### Pattern 4: Error Handling
```
Render Video
  ├─ Success → Continue
  └─ Failure → Retry (max 3x)
                ├─ Success → Continue
                └─ Final Failure → Send Alert
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | n8n | Workflow automation |
| MCP Server | FastMCP + mcp-weather | Content creation tools |
| TTS | Chatterbox (existing) | Voice synthesis |
| Video | ffmpeg | Video rendering |
| Review UI | React + FastAPI | Human approval interface |
| Storage | Ceph RBD | File storage |
| Publishing | YouTube Data API v3 | Platform publishing |
| Notifications | Slack API, Email | Alerts and approvals |

---

## Design Principles

### 1. Human-in-the-Loop
Every critical step has optional human review:
- Script quality check
- Audio approval
- Video preview
- Publishing confirmation

### 2. Modular Pipeline
Each step is independent:
- Script generation ≠ voice synthesis
- Can swap TTS engines
- Can add new templates
- Can publish to multiple platforms

### 3. Fail-Safe
n8n provides:
- Automatic retries
- Error notifications
- Workflow pause/resume
- Manual intervention points

### 4. Template-Driven
Video templates are data, not code:
- Easy to create new styles
- Non-developers can modify
- A/B testing different layouts

### 5. API-First
All components expose APIs:
- MCP tools for AI agents
- REST APIs for integrations
- Webhooks for event-driven
- Easy to extend

---

## Scalability Considerations

### Video Rendering
- **CPU-Intensive**: Large workers with many cores
- **Parallel Jobs**: Queue multiple renders
- **Template Caching**: Pre-load frequently used assets

### Voice Synthesis
- **GPU Scheduling**: Kubernetes GPU affinity
- **Batch Processing**: Combine multiple TTS calls
- **Voice Cloning Cache**: Reuse loaded models

### n8n Workflows
- **Queue Mode**: Handle high volumes
- **Worker Nodes**: Scale n8n workers
- **Rate Limiting**: Respect API quotas

---

## Security Considerations

### Secrets Management
```
Kubernetes Secrets:
├── youtube-api-credentials
├── mxwhisper-api-key
├── bible-mcp-api-key
├── slack-webhook-url
└── s3-access-keys
```

### Access Control
- Review app: Authenticated users only
- Webhooks: Signed/token-based
- MCP servers: API key authentication
- Published videos: Can be private/unlisted

---

## Monitoring & Observability

### Key Metrics
- Scripts generated per day
- Voice synthesis duration/cost
- Video render time/success rate
- YouTube publish success rate
- Human approval time (SLA)
- Storage usage trends

### Alerting
- Render failures
- YouTube API quota exceeded
- Review pending > 24 hours
- Storage nearing capacity

---

## Future Enhancements

1. **Multi-Platform Publishing**: TikTok, Instagram, Facebook
2. **Thumbnail Generation**: AI-generated thumbnails
3. **A/B Testing**: Test different titles/thumbnails
4. **Analytics Integration**: Track video performance
5. **Automated Scheduling**: Optimal publish times
6. **Multi-Language**: Generate videos in multiple languages
7. **Interactive Elements**: YouTube cards, end screens
8. **Podcast Export**: Audio-only versions

---

## Related Documents

- [MxWhisper Architecture](MXWHISPER_ARCHITECTURE.md)
- [Ecosystem Integration](ECOSYSTEM_ARCHITECTURE.md) (next)
- [n8n Workflow Patterns](N8N_WORKFLOW_PATTERNS.md) (next)
- [Chatterbox Docker](../../chatterbox-docker/README.md)

---

**Document Status**: Architecture Planning
**Last Updated**: 2025-10-19
**Version**: 1.0
