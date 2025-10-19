# MxWhisper & MxPodcaster Planning Documents

## Overview
Complete architecture and planning documentation for the MxWhisper knowledge base system and MxPodcaster content creation pipeline.

---

## Document Index

### Core Architecture Documents

#### 1. [MxWhisper Architecture](MXWHISPER_ARCHITECTURE.md)
**Purpose**: Knowledge base and transcription system

**Key Topics**:
- Audio transcription pipeline (Whisper AI)
- Semantic chunking and embeddings
- AI-powered topic categorization
- Collection management
- Vector search architecture
- MCP server for AI-native access
- Temporal workflow orchestration

**Target Audience**: Backend developers, DevOps

---

#### 2. [MxPodcaster Architecture](MXPODCASTER_ARCHITECTURE.md)
**Purpose**: Content creation and publishing system

**Key Topics**:
- Script generation from knowledge base
- Voice synthesis (Chatterbox TTS)
- Video rendering pipeline (ffmpeg)
- Human review workflow
- YouTube publishing automation
- n8n orchestration integration

**Target Audience**: Content creators, automation engineers

---

#### 3. [Ecosystem Architecture](ECOSYSTEM_ARCHITECTURE.md)
**Purpose**: How all systems integrate together

**Key Topics**:
- System boundaries and responsibilities
- Integration patterns (MCP tool chains, n8n workflows, event-driven)
- Complete data flows (sermon upload → YouTube publish)
- Service communication matrix
- Kubernetes deployment topology
- Monitoring and observability
- Error handling and resilience

**Target Audience**: System architects, DevOps, project managers

---

#### 4. [n8n Workflow Patterns](N8N_WORKFLOW_PATTERNS.md)
**Purpose**: Practical workflow examples and patterns

**Key Topics**:
- Daily devotional workflow (scheduled)
- Sermon video production (event-driven)
- Bulk series creation (manual trigger)
- Error recovery patterns
- Reusable sub-workflows
- Best practices and monitoring

**Target Audience**: Workflow designers, content automation teams

---

### Implementation Phase Documents

Located in [collections_and_topics/](collections_and_topics/)

#### [Phase 1: Database & Models](collections_and_topics/PHASE_1_DATABASE_AND_MODELS.md)
- PostgreSQL schema design
- SQLAlchemy models
- Indexes and constraints
- Database migration strategy
- Initial topic seed data

**Estimated Effort**: 2-3 days

---

#### [Phase 2: API Endpoints](collections_and_topics/PHASE_2_API_ENDPOINTS.md)
- Topic CRUD (admin-only)
- Collection CRUD (user-owned)
- Job assignment endpoints
- Enhanced filtering and search
- Authorization and permissions

**Estimated Effort**: 4-5 days

---

#### [Phase 3: AI Integration](collections_and_topics/PHASE_3_AI_INTEGRATION.md)
- TopicClassifier service (using chunk summaries)
- CollectionClassifier (series detection)
- Temporal activities
- Workflow integration
- Confidence-based auto-assignment
- User review and feedback

**Estimated Effort**: 5-7 days

---

#### [Phase 4: MCP Server](collections_and_topics/PHASE_4_MCP_SERVER.md)
- MCP server using mcp-weather core pattern
- Automatic feature discovery
- MCP tools for knowledge base interaction
- Dual interface (MCP + REST)
- Claude Desktop integration

**Estimated Effort**: 3-5 days

---

#### [Main Plan: Topic Categorization](collections_and_topics/TOPIC_CATEGORIZATION_PLAN.md)
- Complete feature overview
- Architecture decisions
- Success metrics
- Implementation priority

---

## System Components Map

### MxWhisper Stack
```
┌─────────────────────────────────────┐
│         MxWhisper System            │
├─────────────────────────────────────┤
│ • FastAPI REST API                  │
│ • Temporal Workflows                │
│ • PostgreSQL + pgvector             │
│ • Redis Cache                       │
│ • MCP Server (HTTP mode)            │
│ • Whisper AI Transcription          │
│ • AI Topic Categorization           │
│ • Vector Search                     │
└─────────────────────────────────────┘
```

### MxPodcaster Stack
```
┌─────────────────────────────────────┐
│       MxPodcaster System            │
├─────────────────────────────────────┤
│ • n8n Workflow Orchestrator         │
│ • MCP Server (content tools)        │
│ • Chatterbox TTS (GPU)              │
│ • Video Renderer (ffmpeg)           │
│ • Review App (human approval)       │
│ • YouTube Publishing                │
└─────────────────────────────────────┘
```

### Supporting Systems
```
┌─────────────────────────────────────┐
│      Supporting Infrastructure      │
├─────────────────────────────────────┤
│ • Bible MCP Server                  │
│ • PostgreSQL (shared)               │
│ • Redis (shared)                    │
│ • Temporal (shared)                 │
│ • Kubernetes (RKE2)                 │
│ • Ceph Storage                      │
└─────────────────────────────────────┘
```

---

## Data Flow Summary

### Knowledge Capture Flow (MxWhisper)
```
Audio Upload
    ↓
Whisper Transcription
    ↓
Semantic Chunking + Topic Summaries
    ↓
Generate Embeddings
    ↓
AI Topic Categorization
    ↓
Storage & Indexing
```

### Content Creation Flow (MxPodcaster)
```
Trigger (Schedule/Webhook/Manual)
    ↓
Search MxWhisper + Bible MCP
    ↓
Generate Script (AI)
    ↓
Human Review ✓
    ↓
Voice Synthesis (Chatterbox)
    ↓
Human Review ✓
    ↓
Video Rendering (ffmpeg)
    ↓
Human Review ✓
    ↓
Publish to YouTube
```

---

## Integration Patterns

### Pattern 1: AI Agent via MCP
```
Claude Desktop
    ↓ (MCP stdio)
User: "Create video about Romans 3"
    ↓
Claude uses MCP tools:
    ├─ search_knowledge_base()
    ├─ get_bible_passage()
    ├─ generate_video_script()
    ├─ create_narration()
    ├─ render_video()
    └─ publish_to_youtube()
```

### Pattern 2: Automated via n8n
```
Schedule/Webhook Trigger
    ↓
n8n Workflow
    ├─ Calls MxWhisper MCP (HTTP)
    ├─ Calls Bible MCP (HTTP)
    ├─ Calls MxPodcaster MCP (HTTP)
    ├─ Human review gates
    └─ Notifications
```

### Pattern 3: Event-Driven
```
User uploads sermon
    ↓
MxWhisper processes
    ↓
Fires webhook on completion
    ↓
n8n workflow activates
    ↓
Creates video automatically
```

---

## Technology Stack

### Languages & Frameworks
- **Python 3.10+**: Backend services, AI/ML
- **FastAPI**: REST APIs
- **TypeScript/JavaScript**: n8n workflows, MCP servers
- **React**: Review app frontend

### AI & ML
- **Whisper AI**: Audio transcription
- **Sentence Transformers**: Text embeddings
- **Claude/GPT-4**: Topic categorization, script generation
- **Chatterbox TTS**: Voice synthesis (open-source)

### Data & Storage
- **PostgreSQL 16**: Primary database
- **pgvector**: Vector search extension
- **Redis 7**: Caching and sessions
- **Ceph RBD**: Persistent storage

### Orchestration & Workflows
- **Temporal**: Durable workflow engine
- **n8n**: Visual workflow automation
- **Kubernetes (RKE2)**: Container orchestration

### Video & Media
- **ffmpeg**: Video rendering
- **Chatterbox**: TTS with voice cloning
- **YouTube Data API v3**: Publishing

### Protocols & Patterns
- **MCP (Model Context Protocol)**: AI-native interfaces
- **FastMCP + mcp-weather core**: MCP server framework
- **REST**: HTTP APIs
- **Webhooks**: Event-driven integration

---

## Deployment Environment

### Kubernetes Cluster
- **Distribution**: RKE2
- **Namespace**: `ai-services`
- **Storage**: Ceph RBD (`ceph-rbd-fast`)
- **Ingress**: NGINX
- **Domain**: `mixwarecs-home.net`

### Infrastructure Components (Pre-existing)
- PostgreSQL server (separate databases)
- Redis server (separate namespaces)
- Temporal server (separate namespaces)
- n8n (already deployed)

### New Components to Deploy
- MxWhisper API + Workers
- MxWhisper MCP Server
- MxPodcaster MCP Server
- Chatterbox TTS
- Video Renderer
- Review App

---

## Development Roadmap

### Phase 1-4: MxWhisper Core (11-15 days)
- Database and models
- API endpoints
- AI categorization
- MCP server

### Phase 5: MxPodcaster System (TBD)
- Content creation tools
- Video pipeline
- Review workflow
- Publishing automation

### Phase 6: Integration & Workflows (TBD)
- n8n workflow templates
- Error handling
- Monitoring
- Optimization

---

## Success Metrics

### MxWhisper
- Transcription accuracy: >95%
- Topic categorization acceptance: >80%
- Search relevance: User satisfaction >85%
- Processing time: <30 min per hour of audio

### MxPodcaster
- Video creation time: <15 min per video
- Human review SLA: <24 hours
- Publishing success rate: >98%
- YouTube publish reliability: >99%

### Ecosystem
- End-to-end reliability: >95%
- API uptime: >99.9%
- User satisfaction: >90%

---

## Next Steps

1. **Review Plans**: Stakeholder review of architecture documents
2. **Validate Assumptions**: Confirm infrastructure availability
3. **Prioritize Features**: Determine MVP scope
4. **Begin Phase 1**: Database and models implementation
5. **Iterate**: Build, test, refine based on feedback

---

## Document Maintenance

### Versioning
All documents include:
- Version number (e.g., v1.0)
- Last updated date
- Document status (Planning, Active, Archived)

### Updates
Documents should be updated when:
- Architecture decisions change
- New features are added
- Technology choices evolve
- Deployment patterns change

### Review Cycle
- **Quarterly**: Architecture review
- **Monthly**: Implementation progress
- **As-needed**: Major changes or pivots

---

## Questions & Feedback

For questions about these plans:
- Architecture decisions: Review system architecture docs
- Implementation details: Review phase-specific docs
- Workflow design: Review n8n patterns doc
- Integration patterns: Review ecosystem architecture

---

**Created**: 2025-10-19
**Status**: Architecture Planning Phase
**Next Review**: Before Phase 1 implementation begins
