# Phase 3: AI Integration

## Overview
Integrate AI-powered topic classification and collection suggestion into the transcription workflow using existing chunk summaries.

## Goals
- Build TopicClassifier service using chunk summaries
- Build CollectionClassifier for series detection
- Create Temporal activities for categorization
- Integrate into transcription workflow (conditional execution)
- Store AI confidence scores and reasoning
- Enable user review and feedback loop

---

## 3.1 Topic Classification Service

### TopicClassifier Architecture

```python
class TopicClassifier:
    """
    AI service for automatic topic assignment using chunk summaries.
    Leverages existing chunk topic summaries to avoid redundant LLM calls.
    """

    async def classify(
        self,
        job_id: int,
        chunk_summaries: List[str],
        available_topics: List[Topic]
    ) -> List[TopicAssignment]:
        """
        Classify job into topics using chunk summaries.

        Args:
            job_id: Job to classify
            chunk_summaries: Pre-existing topic summaries from chunks
            available_topics: All available topics from database

        Returns:
            List of topic assignments with confidence scores
        """
```

### Classification Strategy

**Step 1: Aggregate Chunk Summaries**
```python
def aggregate_summaries(self, chunk_summaries: List[str]) -> str:
    """
    Combine chunk summaries into a coherent overview.

    Example input:
    - "Discussion of Romans chapter 1 about righteousness"
    - "Explanation of faith and works in Romans"
    - "Prayer and reflection on biblical teachings"

    Example output:
    "This content covers Romans chapters with focus on righteousness,
    faith, and works, including prayer and biblical reflection."
    """
    # Simple concatenation or smart aggregation
    return "\n".join(chunk_summaries)
```

**Step 2: Build Topic Hierarchy Context**
```python
def build_topic_context(self, topics: List[Topic]) -> str:
    """
    Create hierarchical topic description for LLM.

    Example output:
    "Available topics:
    1. Religious
       1.1 Bible Study - Bible studies and scriptural analysis
       1.2 Sermons - Sermons and preaching
       1.3 Prayer - Prayer and devotional content
    2. Educational
       2.1 Courses - Educational courses and lectures
    ..."
    """
```

**Step 3: LLM Classification**
```python
async def call_llm(
    self,
    aggregated_summary: str,
    topic_context: str
) -> List[TopicAssignment]:
    """
    Call LLM to classify content into topics.

    Prompt template:
    '''
    Based on the following content summary, assign appropriate topics
    from the available topic hierarchy. Provide confidence scores (0-1)
    and reasoning for each assignment.

    Content Summary:
    {aggregated_summary}

    Available Topics:
    {topic_context}

    Respond with JSON:
    [
      {
        "topic_id": 2,
        "topic_name": "Bible Study",
        "confidence": 0.92,
        "reasoning": "Content discusses biblical teachings about Romans"
      }
    ]
    '''
    """

    # Use OpenAI, Anthropic, or other LLM
    # Parse structured JSON response
    # Return TopicAssignment objects
```

### TopicAssignment Data Structure

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class TopicAssignment:
    topic_id: int
    topic_name: str
    confidence: Decimal  # 0.00 - 1.00
    reasoning: str

    def should_auto_assign(self) -> bool:
        """Auto-assign if confidence > 0.8"""
        return self.confidence > Decimal('0.80')

    def needs_review(self) -> bool:
        """Flag for review if confidence between 0.6 and 0.8"""
        return Decimal('0.60') < self.confidence <= Decimal('0.80')
```

---

## 3.2 Collection Classification Service

### CollectionClassifier Architecture

```python
class CollectionClassifier:
    """
    AI service for suggesting collection membership and detecting series.
    """

    async def suggest_collections(
        self,
        job_id: int,
        job_metadata: Dict[str, Any],
        user_collections: List[Collection],
        chunk_summaries: List[str]
    ) -> CollectionSuggestions:
        """
        Suggest if job belongs to existing collections or should create new one.

        Args:
            job_id: Job to analyze
            job_metadata: Job title, filename, etc.
            user_collections: User's existing collections
            chunk_summaries: Pre-existing chunk summaries

        Returns:
            Suggestions for collection membership
        """
```

### Collection Detection Strategies

**Strategy 1: Pattern Matching (Fast)**
```python
def detect_series_patterns(self, filename: str, title: str) -> Optional[SeriesPattern]:
    """
    Detect common series patterns in filenames/titles.

    Examples:
    - "Romans Chapter 1.mp3" -> Series: "Romans", Episode: 1
    - "Podcast EP042 - Topic.mp3" -> Series: "Podcast", Episode: 42
    - "Course_Week_03.mp3" -> Series: "Course", Episode: 3

    Patterns:
    - "Chapter N"
    - "Episode N" / "EP N"
    - "Part N"
    - "Week N"
    - "Session N"
    """
    patterns = [
        r'(.+?)\s+Chapter\s+(\d+)',
        r'(.+?)\s+EP?(\d+)',
        r'(.+?)\s+Part\s+(\d+)',
        r'(.+?)\s+Week\s+(\d+)',
    ]
    # Return series name and episode number if matched
```

**Strategy 2: Content Similarity (AI-Powered)**
```python
async def find_similar_collections(
    self,
    chunk_summaries: List[str],
    user_collections: List[Collection]
) -> List[CollectionMatch]:
    """
    Use AI to compare content with existing collections.

    For each collection:
    1. Get summaries of existing jobs in collection
    2. Compare new job's summaries with collection's jobs
    3. Calculate similarity score
    4. Return matches above threshold
    """
```

### CollectionSuggestions Data Structure

```python
@dataclass
class CollectionMatch:
    collection_id: int
    collection_name: str
    confidence: Decimal
    reasoning: str
    suggested_position: Optional[int]

@dataclass
class NewCollectionSuggestion:
    suggested_name: str
    collection_type: str  # 'series', 'book', 'course'
    reasoning: str
    confidence: Decimal

@dataclass
class CollectionSuggestions:
    existing_matches: List[CollectionMatch]
    new_collection: Optional[NewCollectionSuggestion]
```

---

## 3.3 Temporal Activities

### Categorization Activity

```python
from temporalio import activity
from dataclasses import dataclass

@dataclass
class CategorizeInput:
    job_id: int
    user_id: int

@dataclass
class CategorizeOutput:
    job_id: int
    topic_assignments: List[TopicAssignment]
    collection_suggestions: CollectionSuggestions
    success: bool
    error: Optional[str]

@activity.defn
async def categorize_job_activity(input: CategorizeInput) -> CategorizeOutput:
    """
    Assign topics and suggest collections using AI analysis.

    Process:
    1. Load job and verify ownership
    2. Load chunks with topic summaries from database
    3. If no chunks exist, return early (nothing to categorize)
    4. Load available topics from database
    5. Load user's existing collections
    6. Run TopicClassifier
    7. Run CollectionClassifier
    8. Store results in database (job_topics table)
    9. Return suggestions for user review
    """

    try:
        # Load data
        job = await get_job(input.job_id)
        chunks = await get_chunks_with_summaries(input.job_id)

        if not chunks or not any(c.topic_summary for c in chunks):
            return CategorizeOutput(
                job_id=input.job_id,
                topic_assignments=[],
                collection_suggestions=CollectionSuggestions([], None),
                success=False,
                error="No chunk summaries available"
            )

        # Extract summaries
        summaries = [c.topic_summary for c in chunks if c.topic_summary]

        # Classify topics
        available_topics = await get_all_topics()
        topic_classifier = TopicClassifier()
        topic_assignments = await topic_classifier.classify(
            job_id=input.job_id,
            chunk_summaries=summaries,
            available_topics=available_topics
        )

        # Suggest collections
        user_collections = await get_user_collections(input.user_id)
        collection_classifier = CollectionClassifier()
        collection_suggestions = await collection_classifier.suggest_collections(
            job_id=input.job_id,
            job_metadata={"title": job.title, "filename": job.filename},
            user_collections=user_collections,
            chunk_summaries=summaries
        )

        # Store topic assignments in database
        for assignment in topic_assignments:
            await create_job_topic(
                job_id=input.job_id,
                topic_id=assignment.topic_id,
                ai_confidence=assignment.confidence,
                ai_reasoning=assignment.reasoning,
                assigned_by=None,  # AI-assigned
                user_reviewed=False
            )

        return CategorizeOutput(
            job_id=input.job_id,
            topic_assignments=topic_assignments,
            collection_suggestions=collection_suggestions,
            success=True,
            error=None
        )

    except Exception as e:
        logger.error(f"Categorization failed for job {input.job_id}: {e}")
        return CategorizeOutput(
            job_id=input.job_id,
            topic_assignments=[],
            collection_suggestions=CollectionSuggestions([], None),
            success=False,
            error=str(e)
        )
```

---

## 3.4 Workflow Integration

### Updated Transcription Workflow

```python
@workflow.defn
class TranscriptionWorkflow:
    """
    Updated workflow with conditional categorization step.

    Flow:
    1. Transcribe audio
    2. Create chunks
    3. Generate embeddings
    4. [NEW] Categorize job (conditional)
    5. Complete
    """

    @workflow.run
    async def run(self, input: TranscriptionInput) -> TranscriptionOutput:
        # Existing steps
        transcription = await workflow.execute_activity(
            transcribe_activity,
            input,
            start_to_close_timeout=timedelta(minutes=30)
        )

        chunks = await workflow.execute_activity(
            create_chunks_activity,
            transcription,
            start_to_close_timeout=timedelta(minutes=5)
        )

        embeddings = await workflow.execute_activity(
            generate_embeddings_activity,
            chunks,
            start_to_close_timeout=timedelta(minutes=10)
        )

        # NEW: Conditional categorization
        if self.should_auto_categorize(input):
            categorization = await workflow.execute_activity(
                categorize_job_activity,
                CategorizeInput(
                    job_id=input.job_id,
                    user_id=input.user_id
                ),
                start_to_close_timeout=timedelta(minutes=2)
            )

            # Log results but don't fail workflow if categorization fails
            if not categorization.success:
                workflow.logger.warning(
                    f"Categorization failed: {categorization.error}"
                )

        return TranscriptionOutput(...)

    def should_auto_categorize(self, input: TranscriptionInput) -> bool:
        """
        Run categorization only if:
        1. User didn't manually assign topics during upload
        2. AI categorization is enabled for this user
        3. Chunks with summaries exist
        """
        return (
            not input.manual_topic_ids and
            input.enable_ai_categorization and
            True  # Chunks always exist after chunking step
        )
```

### Workflow Error Handling

```python
# Categorization failures should NOT fail the entire workflow
# Just log the error and continue

try:
    categorization = await workflow.execute_activity(...)
except Exception as e:
    workflow.logger.error(f"Categorization activity failed: {e}")
    # Continue workflow - categorization is optional
```

---

## 3.5 User Review Interface (API)

### Get AI Suggestions for Job

```
GET /jobs/{id}/suggestions
Authorization: Bearer <token>
```

**Response:**
```json
{
  "job_id": 123,
  "topic_suggestions": [
    {
      "topic_id": 2,
      "topic_name": "Bible Study",
      "confidence": 0.92,
      "reasoning": "Content discusses biblical teachings about Romans",
      "auto_assigned": true,
      "user_reviewed": false
    },
    {
      "topic_id": 5,
      "topic_name": "Sermons",
      "confidence": 0.65,
      "reasoning": "Contains some preaching elements",
      "auto_assigned": false,
      "user_reviewed": false
    }
  ],
  "collection_suggestions": {
    "existing_matches": [
      {
        "collection_id": 1,
        "collection_name": "Romans Bible Study Series",
        "confidence": 0.88,
        "reasoning": "Similar content to existing jobs in this collection",
        "suggested_position": 4
      }
    ],
    "new_collection": {
      "suggested_name": "Bible Study Series",
      "collection_type": "series",
      "confidence": 0.75,
      "reasoning": "Detected series pattern in filename"
    }
  }
}
```

### Accept/Reject Topic Suggestions

**Accept:**
```
POST /jobs/{id}/topics/{topic_id}/accept
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Topic accepted",
  "job_id": 123,
  "topic_id": 2,
  "user_reviewed": true
}
```

**Reject:**
```
DELETE /jobs/{id}/topics/{topic_id}
Authorization: Bearer <token>
```

### Accept Collection Suggestion

```
POST /jobs/{id}/collections/{collection_id}/accept
Authorization: Bearer <token>
```

**Request:**
```json
{
  "position": 4
}
```

### Create New Collection from Suggestion

```
POST /collections
Authorization: Bearer <token>
```

**Request:**
```json
{
  "name": "Bible Study Series",
  "collection_type": "series",
  "add_job_id": 123,
  "position": 1
}
```

---

## 3.6 Confidence-Based Auto-Assignment

### Assignment Strategy

```python
class AssignmentStrategy:
    HIGH_CONFIDENCE_THRESHOLD = Decimal('0.80')
    REVIEW_THRESHOLD = Decimal('0.60')

    async def process_assignment(
        self,
        assignment: TopicAssignment,
        job_id: int
    ):
        """
        Process topic assignment based on confidence level.
        """

        if assignment.confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            # Auto-assign with high confidence
            await self.auto_assign(job_id, assignment)

        elif assignment.confidence >= self.REVIEW_THRESHOLD:
            # Flag for user review (still create record but don't notify)
            await self.flag_for_review(job_id, assignment)

        else:
            # Too low confidence, don't assign
            logger.info(
                f"Skipping low-confidence assignment: "
                f"job={job_id} topic={assignment.topic_id} "
                f"confidence={assignment.confidence}"
            )

    async def auto_assign(self, job_id: int, assignment: TopicAssignment):
        """Create job_topic record with user_reviewed=False"""
        await create_job_topic(
            job_id=job_id,
            topic_id=assignment.topic_id,
            ai_confidence=assignment.confidence,
            ai_reasoning=assignment.reasoning,
            assigned_by=None,
            user_reviewed=False
        )

    async def flag_for_review(self, job_id: int, assignment: TopicAssignment):
        """Same as auto_assign but could trigger notification"""
        await self.auto_assign(job_id, assignment)
        # Optionally: Send notification to user
```

---

## 3.7 Learning & Improvement System

### User Feedback Tracking

```python
@dataclass
class FeedbackEvent:
    job_id: int
    topic_id: int
    action: str  # 'accept', 'reject', 'modify'
    ai_confidence: Decimal
    user_id: int
    timestamp: datetime

async def track_feedback(event: FeedbackEvent):
    """
    Track user feedback for future improvements.

    Storage options:
    1. Separate feedback table in database
    2. Analytics service (e.g., Mixpanel, Amplitude)
    3. Data warehouse for ML training
    """

    # Store in database for analysis
    await create_feedback_record(event)

    # Send to analytics
    analytics.track(
        user_id=event.user_id,
        event="topic_assignment_feedback",
        properties={
            "job_id": event.job_id,
            "topic_id": event.topic_id,
            "action": event.action,
            "ai_confidence": float(event.ai_confidence)
        }
    )
```

### Improvement Strategies

**Phase 3 (Basic):**
- Track acceptance/rejection rates per topic
- Monitor confidence score accuracy
- Log errors and edge cases

**Future Phases:**
- Fine-tune LLM prompts based on feedback
- Build user-specific classification models
- A/B test different classification strategies
- Use feedback to retrain models

---

## 3.8 Performance & Cost Optimization

### Efficiency Metrics

**Chunk-Based Approach Benefits:**
- **No extra LLM calls**: Reuses existing chunk summaries
- **Faster**: Single LLM call per job vs. re-summarizing entire transcript
- **Cheaper**: ~50% cost reduction vs. full document summarization

**Estimated Costs (per job):**
```
Traditional approach:
- Summarize full transcript: ~2000 tokens @ $0.01/1K = $0.02
- Classify into topics: ~500 tokens @ $0.01/1K = $0.005
- Total: ~$0.025 per job

Chunk-based approach:
- Aggregate summaries: 0 tokens (already exist)
- Classify into topics: ~500 tokens @ $0.01/1K = $0.005
- Total: ~$0.005 per job (80% cost reduction)
```

### Caching Strategy

```python
class TopicClassifierCache:
    """Cache classification results to avoid redundant LLM calls"""

    async def get_cached_result(
        self,
        summary_hash: str,
        topic_ids: List[int]
    ) -> Optional[List[TopicAssignment]]:
        """
        Check if we've already classified similar content.

        Cache key: hash(aggregated_summary + topic_ids)
        TTL: 7 days
        """

    async def cache_result(
        self,
        summary_hash: str,
        topic_ids: List[int],
        result: List[TopicAssignment]
    ):
        """Store classification result for future use"""
```

---

## 3.9 Monitoring & Analytics

### Key Metrics

**Categorization Performance:**
- Jobs categorized per day
- Average confidence scores
- Auto-assignment rate (confidence > 0.8)
- Review rate (0.6 < confidence ≤ 0.8)
- Rejection rate (user rejects AI suggestion)

**Accuracy Metrics:**
- Topic acceptance rate (target: >80%)
- Collection suggestion acceptance rate
- False positive rate (assigned but rejected)
- False negative rate (user adds topic AI missed)

**Performance Metrics:**
- Categorization latency (target: <5 seconds)
- LLM API call duration
- Database query performance
- Cache hit rate

### Monitoring Implementation

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
categorizations_total = Counter(
    'categorizations_total',
    'Total number of categorization attempts',
    ['status']  # 'success' or 'failure'
)

topic_assignments_total = Counter(
    'topic_assignments_total',
    'Total topic assignments',
    ['topic_id', 'confidence_level']
)

user_feedback_total = Counter(
    'user_feedback_total',
    'User feedback on AI suggestions',
    ['action']  # 'accept', 'reject', 'modify'
)

# Histograms
categorization_duration = Histogram(
    'categorization_duration_seconds',
    'Time spent categorizing jobs'
)

confidence_score = Histogram(
    'confidence_score',
    'Distribution of AI confidence scores',
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Gauges
pending_reviews = Gauge(
    'pending_reviews',
    'Number of jobs pending user review'
)
```

---

## 3.10 Testing Strategy

### Unit Tests

```python
# Test topic classification
async def test_topic_classifier_high_confidence():
    classifier = TopicClassifier()
    summaries = [
        "Discussion of Romans chapter 1",
        "Biblical analysis of faith and works"
    ]
    topics = [
        Topic(id=1, name="Bible Study"),
        Topic(id=2, name="Sermons")
    ]

    results = await classifier.classify(
        job_id=123,
        chunk_summaries=summaries,
        available_topics=topics
    )

    assert len(results) > 0
    assert results[0].topic_id == 1
    assert results[0].confidence > 0.8

# Test collection pattern detection
def test_detect_series_pattern():
    classifier = CollectionClassifier()

    result = classifier.detect_series_patterns(
        filename="Romans Chapter 3.mp3",
        title="Romans Chapter 3"
    )

    assert result.series_name == "Romans"
    assert result.episode_number == 3
```

### Integration Tests

```python
# Test full categorization workflow
async def test_categorization_activity():
    # Setup: Create job with chunks
    job_id = await create_test_job()
    await create_test_chunks_with_summaries(job_id)

    # Execute activity
    result = await categorize_job_activity(
        CategorizeInput(job_id=job_id, user_id=1)
    )

    # Verify
    assert result.success is True
    assert len(result.topic_assignments) > 0

    # Check database records created
    job_topics = await get_job_topics(job_id)
    assert len(job_topics) > 0
    assert job_topics[0].ai_confidence is not None
```

### End-to-End Tests

```python
# Test full workflow with categorization
async def test_transcription_workflow_with_categorization():
    # Start workflow
    result = await client.execute_workflow(
        TranscriptionWorkflow.run,
        TranscriptionInput(
            job_id=123,
            user_id=1,
            enable_ai_categorization=True,
            manual_topic_ids=None
        ),
        id=f"transcription-{uuid.uuid4()}",
        task_queue="transcription"
    )

    # Verify categorization occurred
    job_topics = await get_job_topics(123)
    assert len(job_topics) > 0
```

---

## Deliverables

- [ ] TopicClassifier service implementation
- [ ] CollectionClassifier service implementation
- [ ] Temporal categorization activity
- [ ] Workflow integration with conditional execution
- [ ] User review API endpoints
- [ ] Confidence-based auto-assignment logic
- [ ] Feedback tracking system
- [ ] Performance monitoring and metrics
- [ ] Caching layer for classification results
- [ ] Unit tests for classifiers
- [ ] Integration tests for activities
- [ ] End-to-end workflow tests
- [ ] Performance benchmarks
- [ ] Documentation for AI models and prompts

---

## Success Criteria

- **Accuracy**: >80% of AI topic assignments accepted by users
- **Coverage**: >90% of eligible jobs get automatic categorization
- **Performance**: <5 second impact on transcription workflow
- **Reliability**: Categorization failures don't break transcription workflow
- **Cost**: 50%+ reduction vs. full document summarization
- **Monitoring**: All key metrics tracked and dashboarded
- **Testing**: >85% code coverage with passing tests

---

## Configuration

### Environment Variables

```bash
# LLM Provider (OpenAI, Anthropic, etc.)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4-turbo-preview

# Categorization settings
ENABLE_AI_CATEGORIZATION=true
HIGH_CONFIDENCE_THRESHOLD=0.80
REVIEW_THRESHOLD=0.60

# Performance settings
CATEGORIZATION_TIMEOUT_SECONDS=120
ENABLE_CLASSIFICATION_CACHE=true
CACHE_TTL_SECONDS=604800  # 7 days
```

---

**Estimated Effort**: 5-7 days
**Dependencies**: Phase 1 (Database), Phase 2 (API)
**Next Steps**: Monitor performance, gather user feedback, iterate on prompts and thresholds
