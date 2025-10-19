# 🎯 AI-Powered Topic Categorization & Collection Management Feature Plan

## Overview
Transform MxWhisper from a transcription service into an **intelligent knowledge management system** that automatically categorizes and organizes audio content using AI, with support for **hierarchical collections** (books, series, courses).

## Implementation Phases

This plan is broken down into four phases:

1. **[Phase 1: Database & Models](PHASE_1_DATABASE_AND_MODELS.md)** - Database schema, SQLAlchemy models, migrations, seed data
2. **[Phase 2: API Endpoints](PHASE_2_API_ENDPOINTS.md)** - RESTful API for topics, collections, assignments, filtering
3. **[Phase 3: AI Integration](PHASE_3_AI_INTEGRATION.md)** - AI classification services, Temporal workflow integration, user review
4. **[Phase 4: MCP Server](PHASE_4_MCP_SERVER.md)** - MCP server for AI-native knowledge base interaction (primary interface)

## Architecture Decisions

### ✅ Chosen Approaches
- **Two-Tier Organization**: Topics (categories) + Collections (knowledge units)
- **Topics**: Admin-managed categories (Bible Study, Sermons, Podcasts)
- **Collections**: User-managed groupings (books, series, courses, albums)
- **Chunk-Based Categorization**: Use existing chunk topic summaries (70% faster, 50% cheaper)
- **AI Auto-Assignment**: Automatic topic/collection detection when not specified
- **Confidence Scoring**: AI provides confidence levels for assignments
- **User Review**: Users can accept/modify AI suggestions
- **Learning System**: Improve future assignments based on user corrections

### ❌ Rejected Approaches
- Full document summarization (too slow/costly)
- Single categorization system (too limiting)
- User-defined topics only (inconsistent categorization)
- No AI assistance (requires manual work)

---

## 📋 Phase 1: Foundation (Database & Models)

### 1.1 Database Schema
```sql
-- Predefined topics table (admin-managed categories)
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INTEGER REFERENCES topics(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- User-managed collections/series (books, courses, podcast seasons, etc.)
CREATE TABLE collections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    collection_type VARCHAR(50), -- 'book', 'course', 'series', 'album', etc.
    user_id INTEGER REFERENCES users(id), -- Owner of the collection
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Job-topic relationships
CREATE TABLE job_topics (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    ai_confidence DECIMAL(3,2),  -- AI confidence score
    ai_reasoning TEXT,          -- Why AI assigned this topic
    assigned_by INTEGER REFERENCES users(id),
    user_reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_id, topic_id)
);

-- Job-collection relationships
CREATE TABLE job_collections (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    position INTEGER,           -- Order within collection (for chapters, episodes)
    assigned_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_id, collection_id)
);

-- Enhanced jobs table
ALTER TABLE jobs ADD COLUMN primary_topic_id INTEGER REFERENCES topics(id);
ALTER TABLE jobs ADD COLUMN collection_id INTEGER REFERENCES collections(id);
```

### 1.2 Data Models
- `Topic` model with hierarchy support (admin-managed)
- `Collection` model for user-managed groupings
- `JobTopic` model with confidence tracking
- `JobCollection` model with ordering support
- Update `Job` model with primary topic and collection references
- New dataclasses for categorization and collection activities

---

## 📋 Phase 2: Core AI Service

### 2.1 Dual Classification Services
```python
class TopicClassifier:
    """AI service for automatic topic assignment using chunk summaries."""

class CollectionClassifier:
    """AI service for suggesting collection membership based on content patterns."""

    async def suggest_collections(
        job_content: str,
        user_collections: List[Collection],
        chunk_summaries: List[str]
    ) -> List[CollectionSuggestion]:
        # Analyze if content belongs to existing user collections
        # Suggest new collection creation if content seems like a series
```

### 2.2 Enhanced Categorization Activity
```python
@activity.defn
async def categorize_and_collect_activity(input: CategorizeInput):
    """
    Assign both topics and collections using AI analysis.

    Process:
    1. Load chunks with topic summaries from DB
    2. Assign topics using predefined topic hierarchy
    3. Analyze for collection membership (existing or new suggestions)
    4. Store both topic
---

## 📋 Phase 3: Workflow Integration

### 3.1 Update Transcription Workflow
```
Current: Transcribe → Chunk → Embed
New:     Transcribe → Chunk → Categorize → Embed
```

### 3.2 Conditional Execution
```python
# Only run categorization if:
# - No manual topics provided by user
# - AI categorization is enabled
# - Chunks exist with topic summaries
if should_auto_categorize(job):
    await categorize_transcript_activity(job_id)
```

### 3.3 Error Handling
- Graceful fallback if categorization fails
- Mark jobs as needing manual review
- Continue workflow even if categorization fails

---

## 📋 Phase 4: API Enhancements

### 4.1 Topic Management
```
GET    /topics           # List all topics (hierarchical)
POST   /topics           # Create topic (admin only)
PUT    /topics/{id}      # Update topic
DELETE /topics/{id}      # Delete topic
```

### 4.2 Collection Management
```
GET    /collections           # List all collections for user
POST   /collections           # Create new collection
PUT    /collections/{id}      # Update collection
DELETE /collections/{id}      # Delete collection
```

### 4.3 Job Topic Assignment
```
POST   /upload           # Accept optional topic_ids parameter
POST   /jobs/{id}/topics # Assign topics to existing job
DELETE /jobs/{id}/topics/{topic_id} # Remove assignment
GET    /jobs/{id}/topics # Get job's topics with confidence
```

### 4.4 Job Collection Assignment
```
POST   /jobs/{id}/collections # Assign collection to existing job
DELETE /jobs/{id}/collections/{collection_id} # Remove assignment
GET    /jobs/{id}/collections # Get job's collections
```

### 4.5 Enhanced Job Listings
```
GET /user/jobs?topic=1              # Filter by topic
GET /user/jobs?needs_review=true    # Jobs needing topic review
GET /search?topics=[1,2,3]          # Search within topics
GET /search?collections=[1,2]       # Search within collections
```

---

## 📋 Phase 5: User Experience

### 5.1 Upload Flow
1. User uploads file (topics optional)
2. If no topics: AI analyzes and suggests
3. User sees suggestions on completion
4. Can accept, modify, or reject

### 5.2 Review Interface
```json
{
  "job_id": 123,
  "ai_suggestions": [
    {
      "topic": "Bible Study",
      "confidence": 0.92,
      "reasoning": "Content discusses biblical teachings about Jesus"
    }
  ],
  "user_can_modify": true
}
```

### 5.3 Topic-Based Navigation
- Browse jobs by topic hierarchy
- Topic statistics and analytics
- Smart search with topic filtering

### 5.4 Collection Management Interface
- Create, update, delete collections
- Add/remove jobs to collections
- Reorder jobs within collections

---

## 📋 Phase 6: Intelligence & Learning

### 6.1 Confidence-Based Decisions
```python
# Auto-assign high-confidence topics
if assignment.confidence > 0.8:
    auto_assign_topic(job_id, topic_id)

# Flag uncertain assignments for review
elif assignment.confidence > 0.6:
    flag_for_review(job_id, topic_id)
```

### 6.2 Learning System
- Track user acceptance/rejection patterns
- Learn topic and collection preferences per user
- Improve future AI assignments
- A/B test different categorization strategies

### 6.3 Analytics
- Topic and collection usage statistics
- Categorization accuracy metrics
- User behavior insights

---

## 📋 Phase 7: Testing & Deployment

### 7.1 Test Cases
- Topic and collection assignment accuracy testing
- Performance benchmarking (vs. manual categorization)
- Edge cases (very short/long content, ambiguous topics)
- User acceptance workflows

### 7.2 Migration Strategy
- Seed initial topic hierarchy
- Gradual rollout of AI categorization
- Backward compatibility for existing jobs

### 7.3 Monitoring
- Categorization success rates
- User engagement with topics and collections
- Performance impact on transcription workflow

---

## 🎯 Success Metrics

- **Accuracy**: >80% of AI topic and collection assignments accepted by users
- **Coverage**: >90% of uploads get automatic categorization
- **Performance**: <5 second impact on total transcription time
- **Usage**: >70% of users engage with topic and collection features

---

## 🚀 Implementation Priority

1. **[Phase 1: Database & Models](PHASE_1_DATABASE_AND_MODELS.md)** (2-3 days)
   - Database schema, indexes, migrations
   - SQLAlchemy models
   - Seed data for initial topics

2. **[Phase 2: API Endpoints](PHASE_2_API_ENDPOINTS.md)** (4-5 days)
   - Topic CRUD (admin-only)
   - Collection CRUD (user-owned)
   - Assignment endpoints
   - Enhanced filtering and search

3. **[Phase 3: AI Integration](PHASE_3_AI_INTEGRATION.md)** (5-7 days)
   - TopicClassifier service
   - CollectionClassifier service
   - Temporal workflow integration
   - User review and feedback system

**Total Estimated Effort**: 11-15 days

---

## 💡 Key Technical Insights

### Efficiency Optimization
- **Chunk-Based Approach**: 70% faster than full summarization
- **No Extra LLM Calls**: Leverages existing chunk topic summaries
- **Smart Aggregation**: Combines chunk summaries for holistic understanding

### AI Quality Improvements
- **Distributed Intelligence**: Multiple chunk summaries provide better context
- **Confidence Scoring**: Transparent decision-making
- **Learning Loop**: Continuous improvement from user feedback

### User Experience Focus
- **Zero Friction**: Automatic categorization when topics not specified
- **Review & Control**: Users can always modify AI suggestions
- **Progressive Enhancement**: Works with or without user input

---

## 📈 Expected Impact

This feature transforms MxWhisper into a **proactively intelligent** system that not only transcribes audio but **understands and organizes** content automatically, providing users with:

- **Smart Organization**: Content finds its place automatically
- **Enhanced Discovery**: Better search through intelligent categorization
- **Knowledge Management**: Topic and collection-based content libraries
- **Time Savings**: No manual categorization required
- **Scalability**: Handles large content libraries intelligently

---

*Document Version: 1.0*
*Last Updated: October 18, 2025*
*Status: Ready for Phase 1 Implementation*