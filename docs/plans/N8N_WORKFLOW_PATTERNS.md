# n8n Workflow Patterns for MxWhisper & MxPodcaster

## Overview
Practical workflow patterns and examples for orchestrating content creation using n8n with MxWhisper and MxPodcaster systems.

---

## Workflow Design Principles

### 1. Modularity
Break workflows into reusable sub-workflows:
- `get-bible-passage` (sub-workflow)
- `search-knowledge-base` (sub-workflow)
- `human-review` (sub-workflow)
- `publish-to-youtube` (sub-workflow)

### 2. Error Handling
Every external call should have:
- Retry logic (3 attempts with exponential backoff)
- Error notification (Slack/email)
- Fallback strategy when possible

### 3. Human-in-the-Loop
Critical decision points need:
- Webhook pause nodes
- Preview interfaces
- Approval/rejection webhooks
- Timeout handling (default action after 48h)

### 4. Observable Execution
Track progress with:
- Status updates in database
- Slack notifications at key milestones
- Error logging
- Execution time tracking

---

## Pattern 1: Daily Devotional (Scheduled)

### Workflow Overview
```
Trigger: Cron (Daily 6:00 AM)
Duration: ~10-15 minutes
Human Review: Optional
Output: YouTube video (scheduled for 10 AM)
```

### Node Flow

#### 1. Schedule Trigger
```javascript
// Cron: 0 6 * * *
// Monday-Saturday at 6:00 AM
{
  "cronExpression": "0 6 * * 1-6",
  "timezone": "America/New_York"
}
```

#### 2. Get Today's Bible Reading
```javascript
// HTTP Request Node
POST http://bible-mcp.ai-services.svc.cluster.local:3000/mcp/tools/get_daily_reading
{
  "date": "{{ $today.format('YYYY-MM-DD') }}"
}

// Returns:
{
  "passage": "Romans 3:23-24",
  "text": "for all have sinned...",
  "version": "ESV"
}
```

#### 3. Search Related Content
```javascript
// HTTP Request Node
POST http://mxwhisper-mcp.ai-services.svc.cluster.local:3000/mcp/tools/search_knowledge_base
{
  "query": "{{ $json.passage }} grace justification",
  "topic_ids": [2, 5],  // Bible Study, Sermons
  "limit": 5
}

// Returns:
{
  "results": [
    {"job_id": 123, "title": "...", "excerpt": "..."},
    ...
  ]
}
```

#### 4. Generate Script
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/generate_video_script
{
  "bible_passage": "{{ $('Get Today's Bible Reading').item.json.passage }}",
  "version": "ESV",
  "search_results": "{{ $('Search Related Content').item.json.results }}",
  "style": "devotional",
  "duration": "2-3 minutes",
  "tone": "encouraging"
}

// Returns:
{
  "script": "Good morning...",
  "sections": [...],
  "estimated_duration": 150,
  "bible_references": ["Romans 3:23-24"]
}
```

#### 5. IF: Auto-Approve or Review
```javascript
// If Node: Check if auto-approve enabled
{{ $json.config.auto_approve_scripts === true }}

// IF TRUE → Skip to narration
// IF FALSE → Human review
```

#### 6A. Human Script Review (Optional)
```javascript
// HTTP Request: Create Review
POST http://review-app.ai-services.svc.cluster.local:8000/reviews
{
  "type": "script",
  "content": "{{ $json.script }}",
  "workflow_id": "{{ $workflow.id }}",
  "execution_id": "{{ $execution.id }}"
}

// Slack Notification
POST <slack_webhook_url>
{
  "text": "📝 Daily devotional script ready for review",
  "attachments": [{
    "text": "{{ $json.script.substring(0, 500) }}...",
    "actions": [
      {"text": "Review", "url": "https://review.app/{{ $json.review_id }}"}
    ]
  }]
}

// Wait for Webhook
// Webhook Node: /webhook/approve-script/{{ $json.review_id }}
// Timeout: 2 hours
// On timeout: Auto-approve and continue
```

#### 7. Generate Narration
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/create_narration
{
  "script_text": "{{ $json.script }}",
  "voice_profile": "default",
  "emotion": "calm",
  "exaggeration": 0.4
}

// Returns:
{
  "audio_url": "s3://audio/devotional_20251019.wav",
  "duration": 152.5,
  "sample_rate": 24000
}
```

#### 8. Render Video
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/render_video
{
  "audio_url": "{{ $json.audio_url }}",
  "template": "devotional",
  "text_overlays": [
    {
      "text": "{{ $('Get Today's Bible Reading').item.json.passage }}",
      "position": "top",
      "start": 0,
      "end": 5
    }
  ],
  "background_image": "cross-sunrise.jpg",
  "subtitles": true
}

// Returns:
{
  "video_url": "s3://videos/devotional_20251019.mp4",
  "duration": 152.5,
  "filesize_mb": 28.3
}
```

#### 9. Publish to YouTube
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/publish_to_youtube
{
  "video_url": "{{ $json.video_url }}",
  "title": "Daily Devotional - {{ $('Get Today's Bible Reading').item.json.passage }}",
  "description": "Today's reflection on {{ $('Get Today's Bible Reading').item.json.passage }}",
  "tags": ["Daily Devotional", "Bible Study", "Faith"],
  "category": "Education",
  "scheduled_publish": "{{ $today.plus(4, 'hours').toISO() }}"  // 10 AM
}

// Returns:
{
  "youtube_id": "abc123",
  "url": "https://youtube.com/watch?v=abc123",
  "status": "scheduled",
  "scheduled_for": "2025-10-19T10:00:00Z"
}
```

#### 10. Success Notification
```javascript
// Slack Notification
POST <slack_webhook_url>
{
  "text": "✅ Daily devotional created and scheduled!",
  "attachments": [{
    "fields": [
      {"title": "Passage", "value": "{{ $('Get Today's Bible Reading').item.json.passage }}"},
      {"title": "YouTube", "value": "{{ $json.url }}"},
      {"title": "Scheduled", "value": "10:00 AM"}
    ]
  }]
}
```

---

## Pattern 2: Sermon Video Production (Event-Driven)

### Workflow Overview
```
Trigger: Webhook (sermon_completed from MxWhisper)
Duration: ~20-30 minutes + human review time
Human Review: Required (3 stages)
Output: YouTube video (added to series playlist)
```

### Node Flow

#### 1. Webhook Trigger
```javascript
// Webhook URL: /webhook/sermon-completed
// Method: POST
// Authentication: Header Auth

// Incoming payload:
{
  "event": "sermon_completed",
  "job_id": 123,
  "collection_id": 5,
  "position": 3,
  "title": "Romans 3 - Justified by Grace"
}
```

#### 2. Get Job Details
```javascript
// HTTP Request Node
POST http://mxwhisper-mcp.ai-services.svc.cluster.local:3000/mcp/tools/get_job
{
  "job_id": {{ $json.job_id }}
}

// Returns job with topics, collections, transcript summary
```

#### 3. Get Collection Context
```javascript
// HTTP Request Node
POST http://mxwhisper-mcp.ai-services.svc.cluster.local:3000/mcp/tools/get_collection
{
  "collection_id": {{ $json.collection_id }}
}

// Returns:
{
  "id": 5,
  "name": "Romans Study Series",
  "jobs": [
    {"position": 1, "title": "Romans 1 - Introduction"},
    {"position": 2, "title": "Romans 2 - God's Judgment"},
    {"position": 3, "title": "Romans 3 - Justified by Grace"}  // Current
  ]
}
```

#### 4. Extract Scripture References
```javascript
// Function Node: Extract verses mentioned in transcript
const transcript = $('Get Job Details').item.json.transcript;
const versePattern = /([1-3]?\s?[A-Z][a-z]+)\s(\d+):(\d+(?:-\d+)?)/g;
const verses = transcript.match(versePattern) || [];

return {
  primary_verse: verses[0] || "Romans 3:23-24",
  all_verses: verses
};
```

#### 5. Get Bible Passages
```javascript
// HTTP Request Node (Loop over verses)
POST http://bible-mcp.ai-services.svc.cluster.local:3000/mcp/tools/get_passage
{
  "passage": "{{ $json.primary_verse }}",
  "version": "ESV"
}
```

#### 6. Generate Sermon Script
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/generate_video_script
{
  "mxwhisper_job_id": {{ $('Webhook Trigger').item.json.job_id }},
  "collection_context": {{ $('Get Collection Context').item.json }},
  "bible_passages": {{ $('Get Bible Passages').all() }},
  "style": "sermon",
  "duration": "8-10 minutes",
  "tone": "teaching",
  "include_intro": true,  // Series intro
  "include_recap": true   // Previous episodes recap
}

// Returns comprehensive sermon script
```

#### 7. STAGE 1: Script Review
```javascript
// Create Review
POST http://review-app.ai-services.svc.cluster.local:8000/reviews
{
  "type": "script",
  "workflow_id": "{{ $workflow.id }}",
  "content": {{ $json }}
}

// Slack Notification
POST <slack_webhook_url>
{
  "text": "📝 Sermon script ready: Romans 3 (Episode 3/12)",
  "blocks": [
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "*Preview:*\n{{ $json.script.substring(0, 300) }}..."}
    },
    {
      "type": "actions",
      "elements": [
        {"type": "button", "text": "Review Script", "url": "https://review.app/{{ $json.review_id }}"}
      ]
    }
  ]
}

// Wait for Webhook: /webhook/approve-script/{{ $json.review_id }}
// Timeout: 48 hours
// On timeout: Send reminder Slack message
```

#### 8. Generate Voice (Pastor's Voice Clone)
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/create_narration
{
  "script_text": "{{ $json.approved_script }}",
  "voice_profile": "pastor_john",  // Reference: /voices/pastor_john.wav
  "emotion": "thoughtful",
  "exaggeration": 0.5
}
```

#### 9. STAGE 2: Audio Review
```javascript
// Create Review
POST http://review-app.ai-services.svc.cluster.local:8000/reviews
{
  "type": "audio",
  "audio_url": "{{ $json.audio_url }}",
  "duration": {{ $json.duration }}
}

// Slack: Audio player link
// Wait for Webhook: /webhook/approve-audio/{{ $json.review_id }}
```

#### 10. Render Video
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/render_video
{
  "audio_url": "{{ $json.audio_url }}",
  "template": "sermon",
  "text_overlays": [
    {
      "text": "Romans Study Series - Episode 3",
      "position": "top",
      "start": 0,
      "end": 5
    },
    {
      "text": "{{ $('Extract Scripture References').item.json.primary_verse }}",
      "position": "top_center",
      "start": 10,
      "end": 15
    }
  ],
  "background_image": "sermon_series_background.jpg",
  "subtitles": true,
  "chapters": [
    {"time": 0, "title": "Introduction"},
    {"time": 60, "title": "Scripture Reading"},
    {"time": 120, "title": "Main Teaching"},
    {"time": 420, "title": "Application"}
  ]
}
```

#### 11. STAGE 3: Video Review
```javascript
// Create Review
POST http://review-app.ai-services.svc.cluster.local:8000/reviews
{
  "type": "video",
  "video_url": "{{ $json.video_url }}",
  "metadata": {
    "duration": {{ $json.duration }},
    "filesize_mb": {{ $json.filesize_mb }}
  }
}

// Slack: Video preview player
// Wait for Webhook: /webhook/approve-video/{{ $json.review_id }}
```

#### 12. Publish to YouTube (with Playlist)
```javascript
// HTTP Request Node
POST http://mxpodcaster-mcp.ai-services.svc.cluster.local:3000/mcp/tools/publish_to_youtube
{
  "video_url": "{{ $json.video_url }}",
  "title": "Romans 3: Justified by Grace | Romans Study Series",
  "description": `Episode 3 of our Romans Study Series.

{{ $('Generate Sermon Script').item.json.summary }}

📖 Primary Scripture: {{ $('Extract Scripture References').item.json.primary_verse }}

⏮️ Previous Episode: Romans 2 - God's Judgment
⏭️ Next Episode: Coming next week

🎓 Full Series: https://youtube.com/playlist?list=PLxxx`,
  "tags": ["Bible Study", "Romans", "Sermon", "Grace", "Justification"],
  "category": "Education",
  "playlist_id": "PLxxx",  // Romans Study Series playlist
  "scheduled_publish": "{{ $today.plus(3, 'days').set({hour: 18, minute: 0}).toISO() }}"
}
```

#### 13. Update MxWhisper Job Metadata
```javascript
// HTTP Request Node
POST http://mxwhisper-api.ai-services.svc.cluster.local:8000/jobs/{{ $('Webhook Trigger').item.json.job_id }}/metadata
{
  "youtube_url": "{{ $json.url }}",
  "youtube_id": "{{ $json.youtube_id }}",
  "published": true,
  "published_at": "{{ $json.scheduled_for }}"
}
```

#### 14. Success Notification
```javascript
// Slack Notification
POST <slack_webhook_url>
{
  "text": "✅ Sermon video published!",
  "blocks": [
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Series:* Romans Study Series"},
        {"type": "mrkdwn", "text": "*Episode:* 3 of 12"},
        {"type": "mrkdwn", "text": "*Title:* Romans 3: Justified by Grace"},
        {"type": "mrkdwn", "text": "*Scheduled:* {{ $json.scheduled_for }}"},
        {"type": "mrkdwn", "text": "*YouTube:* {{ $json.url }}"}
      ]
    }
  ]
}
```

---

## Pattern 3: Bulk Series Creation (Manual Trigger)

### Workflow Overview
```
Trigger: Manual (form input)
Duration: Variable (N episodes × 15 min)
Human Review: Batch review mode
Output: Complete YouTube playlist
```

### Node Flow

#### 1. Manual Trigger with Form
```javascript
// Manual Trigger Node with Form
{
  "fields": [
    {
      "name": "collection_id",
      "type": "number",
      "required": true,
      "description": "Collection ID to process"
    },
    {
      "name": "episodes_per_day",
      "type": "number",
      "default": 3,
      "description": "How many episodes to publish per day"
    },
    {
      "name": "start_date",
      "type": "date",
      "default": "{{ $today.plus(1, 'week') }}",
      "description": "First publish date"
    }
  ]
}
```

#### 2. Get Collection with All Jobs
```javascript
// HTTP Request Node
POST http://mxwhisper-mcp.ai-services.svc.cluster.local:3000/mcp/tools/get_collection
{
  "collection_id": {{ $json.collection_id }}
}

// Returns collection with all jobs sorted by position
```

#### 3. Split Jobs into Batches
```javascript
// Function Node
const jobs = $json.jobs;
const batchSize = $('Manual Trigger').item.json.episodes_per_day;

const batches = [];
for (let i = 0; i < jobs.length; i += batchSize) {
  batches.push(jobs.slice(i, i + batchSize));
}

return batches.map((batch, index) => ({
  batch_number: index + 1,
  jobs: batch
}));
```

#### 4. Loop: For Each Batch
```javascript
// Loop Over Items Node
// Process each batch sequentially
```

#### 5. Loop: For Each Job in Batch
```javascript
// Nested Loop Over Items Node
// Process jobs in batch in parallel (up to 3 concurrent)
```

#### 6-12. Same as Sermon Pattern
```
Generate Script → Review → Narration → Review → Video → Review → Publish
(But in parallel for batch)
```

#### 13. Calculate Publish Schedule
```javascript
// Function Node
const batchNumber = $('For Each Batch').item.json.batch_number - 1;
const episodeIndex = $('For Each Job in Batch').itemIndex;
const startDate = new Date($('Manual Trigger').item.json.start_date);

// Schedule: First episode at 6 PM, then +1 day for each batch
const publishDate = new Date(startDate);
publishDate.setDate(publishDate.getDate() + batchNumber);
publishDate.setHours(18, 0, 0, 0);

return {
  scheduled_publish: publishDate.toISOString(),
  episode_number: (batchNumber * 3) + episodeIndex + 1
};
```

#### 14. Batch Completion Notification
```javascript
// After each batch completes
POST <slack_webhook_url>
{
  "text": "✅ Batch {{ $json.batch_number }} completed",
  "blocks": [
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "*Episodes processed:* {{ $json.jobs.length }}"}
    }
  ]
}
```

#### 15. Final Summary
```javascript
// After all batches complete
POST <slack_webhook_url>
{
  "text": "🎉 Complete series published!",
  "blocks": [
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Collection:* {{ $('Get Collection').item.json.name }}"},
        {"type": "mrkdwn", "text": "*Total Episodes:* {{ $('Get Collection').item.json.jobs.length }}"},
        {"type": "mrkdwn", "text": "*Playlist:* https://youtube.com/playlist?list=PLxxx"}
      ]
    }
  ]
}
```

---

## Pattern 4: Error Recovery Workflow

### Workflow Overview
```
Trigger: Webhook (error_notification)
Purpose: Retry failed workflows with different parameters
```

### Node Flow

#### 1. Webhook: Error Notification
```javascript
// Incoming payload from failed workflow
{
  "original_workflow_id": "sermon_video_production",
  "execution_id": "exec_123",
  "error": {
    "node": "Generate Narration",
    "message": "Chatterbox timeout",
    "timestamp": "..."
  },
  "context": {
    "job_id": 123,
    "script": "..."
  }
}
```

#### 2. Identify Error Type
```javascript
// Switch Node
{{ $json.error.node }}

// Routes:
// - "Generate Narration" → Try fallback TTS
// - "Render Video" → Retry with lower quality
// - "Publish YouTube" → Check quota, retry later
// - Default → Alert admin
```

#### 3A. Fallback TTS (if Chatterbox failed)
```javascript
// HTTP Request: OpenAI TTS
POST https://api.openai.com/v1/audio/speech
{
  "model": "tts-1",
  "input": "{{ $json.context.script }}",
  "voice": "onyx"
}

// Then continue to video rendering
```

#### 3B. Retry Video Render (lower quality)
```javascript
// HTTP Request
POST http://video-renderer:8080/render
{
  // ... same params but:
  "quality": "medium",  // Instead of "high"
  "resolution": "720p"  // Instead of "1080p"
}
```

#### 3C. Delay YouTube Publish (quota exceeded)
```javascript
// Wait Node: 24 hours
// Then retry publish
```

#### 4. Success/Failure Notification
```javascript
// If recovered successfully:
POST <slack_webhook_url>
{
  "text": "✅ Recovered from error using fallback strategy",
  "attachments": [{
    "color": "good",
    "fields": [
      {"title": "Original Error", "value": "{{ $json.error.message }}"},
      {"title": "Solution", "value": "Used OpenAI TTS fallback"}
    ]
  }]
}

// If still failing:
POST <slack_webhook_url>
{
  "text": "❌ Manual intervention required",
  "attachments": [{
    "color": "danger",
    "text": "{{ $json.error.message }}",
    "actions": [
      {"text": "View Logs", "url": "..."}
    ]
  }]
}
```

---

## Common Sub-Workflows

### Sub-Workflow: Human Review Gate

```javascript
// Reusable across all workflows
// Input: content, type, metadata
// Output: approved_content, changes

// 1. Create Review Record
POST /reviews
{
  "type": "{{ $json.type }}",  // script, audio, video
  "content": "{{ $json.content }}",
  "metadata": {{ $json.metadata }}
}

// 2. Send Notification (Slack)
POST <slack_webhook>
{
  "text": "{{ $json.type }} ready for review",
  "actions": [
    {"text": "Review", "url": "https://review.app/{{ $json.review_id }}"}
  ]
}

// 3. Wait for Webhook
// URL: /webhook/approve/{{ $json.review_id }}
// Timeout: 48 hours
// On timeout: Auto-approve or alert

// 4. Return approved content
return {
  approved: true,
  approved_content: "{{ $json.content }}",
  reviewer: "{{ $json.reviewer_id }}",
  approved_at: "{{ $now }}"
};
```

---

## Best Practices

### 1. Error Handling
```javascript
// Every HTTP Request node should have:
{
  "retry": {
    "enabled": true,
    "maxAttempts": 3,
    "waitBetween": 1000  // exponential backoff
  },
  "errorHandling": {
    "continueOnFail": false,  // Usually false for critical steps
    "onError": "executeErrorWorkflow"  // Trigger error recovery
  }
}
```

### 2. Timeouts
```javascript
// Set appropriate timeouts for each operation:
{
  "transcription": 1800000,     // 30 min
  "script_generation": 120000,   // 2 min
  "narration": 600000,           // 10 min
  "video_render": 3600000,       // 60 min
  "youtube_upload": 1800000      // 30 min
}
```

### 3. Logging & Monitoring
```javascript
// Add tracking nodes after each major step:
POST http://monitoring-api/log
{
  "workflow": "{{ $workflow.name }}",
  "execution_id": "{{ $execution.id }}",
  "step": "{{ $node.name }}",
  "status": "success",
  "duration_ms": "{{ $json.duration }}",
  "timestamp": "{{ $now }}"
}
```

### 4. Idempotency
```javascript
// Always check if operation already completed:
GET /jobs/{{ $json.job_id }}/youtube_url

if ($json.youtube_url) {
  // Already published, skip
  return { status: "already_published", url: $json.youtube_url };
} else {
  // Proceed with publishing
  ...
}
```

### 5. Rate Limiting
```javascript
// Use delay nodes to respect API quotas:
// YouTube: 10,000 quota units/day
// OpenAI: Variable rate limits
// Chatterbox: GPU availability

// Add delay between batch operations:
Wait Node: 60000 ms (1 min between each video upload)
```

---

## Monitoring Dashboard

### Key Metrics to Track in n8n

```javascript
// Workflow executions by status
{
  "total_executions": 1523,
  "successful": 1489,
  "failed": 34,
  "success_rate": 97.7
}

// Average execution times
{
  "daily_devotional": "8.2 min",
  "sermon_video": "22.5 min",
  "bulk_series": "4.5 hours"
}

// Human review SLA
{
  "average_review_time": "2.3 hours",
  "reviews_pending": 3,
  "overdue_reviews": 0
}

// Resource costs
{
  "llm_api_calls": 450,
  "estimated_cost": "$23.50",
  "tts_minutes": 342,
  "video_renders": 45
}
```

---

## Related Documents

- [MxWhisper Architecture](MXWHISPER_ARCHITECTURE.md)
- [MxPodcaster Architecture](MXPODCASTER_ARCHITECTURE.md)
- [Ecosystem Architecture](ECOSYSTEM_ARCHITECTURE.md)

---

**Document Status**: Architecture Planning
**Last Updated**: 2025-10-19
**Version**: 1.0
