# Phase 2: API Endpoints

## Overview
Build RESTful API endpoints for topic and collection management, including assignment operations and enhanced filtering.

## Goals
- Create CRUD endpoints for topics (admin-only)
- Create CRUD endpoints for collections (user-owned)
- Implement job assignment endpoints for topics and collections
- Add filtering and search capabilities
- Ensure proper authentication and authorization

---

## 2.1 Topic Management Endpoints

### List Topics (Hierarchical)
```
GET /topics
```

**Response:**
```json
{
  "topics": [
    {
      "id": 1,
      "name": "Religious",
      "description": "Religious and spiritual content",
      "parent_id": null,
      "children": [
        {
          "id": 2,
          "name": "Bible Study",
          "description": "Bible studies and scriptural analysis",
          "parent_id": 1,
          "children": []
        },
        {
          "id": 3,
          "name": "Sermons",
          "description": "Sermons and preaching",
          "parent_id": 1,
          "children": []
        }
      ]
    }
  ]
}
```

**Features:**
- Returns hierarchical structure (nested children)
- Public endpoint (no auth required)
- Cached for performance

---

### Create Topic (Admin Only)
```
POST /topics
Authorization: Bearer <admin_token>
```

**Request:**
```json
{
  "name": "Bible Study",
  "description": "Bible studies and scriptural analysis",
  "parent_id": 1
}
```

**Response:**
```json
{
  "id": 2,
  "name": "Bible Study",
  "description": "Bible studies and scriptural analysis",
  "parent_id": 1,
  "created_at": "2025-10-18T12:00:00Z"
}
```

**Validation:**
- Require admin role
- Validate name is unique
- Validate parent_id exists (if provided)

---

### Update Topic (Admin Only)
```
PUT /topics/{id}
Authorization: Bearer <admin_token>
```

**Request:**
```json
{
  "name": "Biblical Studies",
  "description": "Updated description"
}
```

**Validation:**
- Require admin role
- Cannot create circular parent references
- Name must remain unique

---

### Delete Topic (Admin Only)
```
DELETE /topics/{id}
Authorization: Bearer <admin_token>
```

**Behavior:**
- Cascade deletes to `job_topics` (removes associations)
- If topic has children, either:
  - Option A: Prevent deletion (return 409 Conflict)
  - Option B: Cascade delete children (destructive)
- **Recommendation**: Prevent deletion if children exist

---

## 2.2 Collection Management Endpoints

### List User Collections
```
GET /collections
Authorization: Bearer <token>
```

**Query Parameters:**
- `?type=book` - Filter by collection type
- `?is_public=true` - Show only public collections

**Response:**
```json
{
  "collections": [
    {
      "id": 1,
      "name": "Romans Bible Study Series",
      "description": "Complete study of the Book of Romans",
      "collection_type": "series",
      "is_public": false,
      "job_count": 12,
      "created_at": "2025-10-18T12:00:00Z",
      "updated_at": "2025-10-18T12:00:00Z"
    }
  ]
}
```

**Features:**
- Returns only user's own collections
- Includes job count for each collection
- Supports filtering by type and visibility

---

### Get Collection Details
```
GET /collections/{id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": 1,
  "name": "Romans Bible Study Series",
  "description": "Complete study of the Book of Romans",
  "collection_type": "series",
  "is_public": false,
  "jobs": [
    {
      "job_id": 101,
      "position": 1,
      "title": "Romans Chapter 1",
      "created_at": "2025-10-01T12:00:00Z"
    },
    {
      "job_id": 102,
      "position": 2,
      "title": "Romans Chapter 2",
      "created_at": "2025-10-02T12:00:00Z"
    }
  ],
  "created_at": "2025-10-18T12:00:00Z",
  "updated_at": "2025-10-18T12:00:00Z"
}
```

**Authorization:**
- User must own the collection OR collection must be public

---

### Create Collection
```
POST /collections
Authorization: Bearer <token>
```

**Request:**
```json
{
  "name": "Romans Bible Study Series",
  "description": "Complete study of the Book of Romans",
  "collection_type": "series",
  "is_public": false
}
```

**Response:**
```json
{
  "id": 1,
  "name": "Romans Bible Study Series",
  "description": "Complete study of the Book of Romans",
  "collection_type": "series",
  "is_public": false,
  "user_id": 42,
  "created_at": "2025-10-18T12:00:00Z"
}
```

**Validation:**
- Name required (max 200 chars)
- collection_type optional (max 50 chars)
- Automatically sets user_id from auth token

---

### Update Collection
```
PUT /collections/{id}
Authorization: Bearer <token>
```

**Request:**
```json
{
  "name": "Romans Study - Updated",
  "description": "Updated description",
  "is_public": true
}
```

**Authorization:**
- User must own the collection

---

### Delete Collection
```
DELETE /collections/{id}
Authorization: Bearer <token>
```

**Behavior:**
- Cascade deletes to `job_collections` (removes job associations)
- Does NOT delete jobs themselves
- User must own the collection

---

## 2.3 Job Topic Assignment Endpoints

### Get Job Topics
```
GET /jobs/{id}/topics
Authorization: Bearer <token>
```

**Response:**
```json
{
  "job_id": 123,
  "topics": [
    {
      "topic_id": 2,
      "name": "Bible Study",
      "ai_confidence": 0.92,
      "ai_reasoning": "Content discusses biblical teachings about Romans",
      "user_reviewed": false,
      "assigned_at": "2025-10-18T12:00:00Z"
    }
  ]
}
```

**Authorization:**
- User must own the job

---

### Assign Topics to Job
```
POST /jobs/{id}/topics
Authorization: Bearer <token>
```

**Request:**
```json
{
  "topic_ids": [2, 5]
}
```

**Response:**
```json
{
  "job_id": 123,
  "assigned_topics": [
    {
      "topic_id": 2,
      "name": "Bible Study",
      "assigned_by": 42,
      "user_reviewed": true
    },
    {
      "topic_id": 5,
      "name": "Sermons",
      "assigned_by": 42,
      "user_reviewed": true
    }
  ]
}
```

**Behavior:**
- Creates JobTopic records with `assigned_by = current_user_id`
- Sets `user_reviewed = true` (manual assignment)
- Ignores duplicates (idempotent)
- User must own the job

---

### Remove Topic from Job
```
DELETE /jobs/{id}/topics/{topic_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Topic removed from job",
  "job_id": 123,
  "topic_id": 2
}
```

**Authorization:**
- User must own the job

---

### Update Topic Review Status
```
PATCH /jobs/{id}/topics/{topic_id}
Authorization: Bearer <token>
```

**Request:**
```json
{
  "user_reviewed": true
}
```

**Use Case:**
- User accepts AI-suggested topic
- Marks `user_reviewed = true` without removing the topic

---

## 2.4 Job Collection Assignment Endpoints

### Get Job Collections
```
GET /jobs/{id}/collections
Authorization: Bearer <token>
```

**Response:**
```json
{
  "job_id": 123,
  "collections": [
    {
      "collection_id": 1,
      "name": "Romans Bible Study Series",
      "position": 3,
      "assigned_at": "2025-10-18T12:00:00Z"
    }
  ]
}
```

---

### Add Job to Collection
```
POST /jobs/{id}/collections
Authorization: Bearer <token>
```

**Request:**
```json
{
  "collection_id": 1,
  "position": 3
}
```

**Response:**
```json
{
  "job_id": 123,
  "collection_id": 1,
  "position": 3,
  "assigned_by": 42,
  "created_at": "2025-10-18T12:00:00Z"
}
```

**Validation:**
- User must own the collection
- User must own the job
- Position is optional (auto-increment if not provided)

---

### Update Job Position in Collection
```
PATCH /jobs/{id}/collections/{collection_id}
Authorization: Bearer <token>
```

**Request:**
```json
{
  "position": 5
}
```

**Use Case:**
- Reorder jobs within a collection

---

### Remove Job from Collection
```
DELETE /jobs/{id}/collections/{collection_id}
Authorization: Bearer <token>
```

**Authorization:**
- User must own the collection

---

## 2.5 Enhanced Job Listings

### Filter Jobs by Topic
```
GET /user/jobs?topic_id=2
Authorization: Bearer <token>
```

**Response:**
```json
{
  "jobs": [
    {
      "id": 123,
      "title": "Sunday Sermon",
      "topics": [
        {"id": 2, "name": "Bible Study"}
      ],
      "created_at": "2025-10-18T12:00:00Z"
    }
  ],
  "total": 15,
  "page": 1
}
```

---

### Filter Jobs by Collection
```
GET /user/jobs?collection_id=1
Authorization: Bearer <token>
```

**Features:**
- Returns jobs in order of `position` field
- Only shows user's own jobs

---

### Filter Jobs Needing Review
```
GET /user/jobs?needs_review=true
Authorization: Bearer <token>
```

**Behavior:**
- Returns jobs with AI-assigned topics where `user_reviewed = false`
- Helps users review AI suggestions

---

## 2.6 Enhanced Search Endpoints

### Search with Topic Filter
```
GET /search?q=romans&topic_ids=2,5
Authorization: Bearer <token>
```

**Behavior:**
- Searches within specified topics only
- Combines semantic search with topic filtering

---

### Search with Collection Filter
```
GET /search?q=chapter&collection_ids=1,2
Authorization: Bearer <token>
```

**Behavior:**
- Searches within specified collections only
- User must own collections OR collections must be public

---

## 2.7 Upload Endpoint Enhancement

### Upload with Topics/Collections
```
POST /upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Form Parameters:**
```
file: <audio_file>
topic_ids: 2,5           # Optional: Pre-assign topics
collection_id: 1         # Optional: Add to collection
position: 3              # Optional: Position in collection
```

**Behavior:**
- If `topic_ids` provided: Skip AI categorization, assign manually
- If `collection_id` provided: Add to collection after transcription
- If neither provided: AI categorization will run (Phase 3)

---

## 2.8 Authorization & Permissions

### Permission Matrix

| Endpoint | Owner | Admin | Public |
|----------|-------|-------|--------|
| GET /topics | ✓ | ✓ | ✓ |
| POST /topics | ✗ | ✓ | ✗ |
| PUT/DELETE /topics | ✗ | ✓ | ✗ |
| GET /collections | ✓ | ✓ | ✗ |
| POST /collections | ✓ | ✓ | ✗ |
| PUT /collections/{id} | Owner only | ✗ | ✗ |
| DELETE /collections/{id} | Owner only | ✗ | ✗ |
| GET /collections/{id} | Owner or if public | ✓ | If public |
| POST /jobs/{id}/topics | Owner only | ✗ | ✗ |
| POST /jobs/{id}/collections | Owner only | ✗ | ✗ |

---

## 2.9 Error Handling

### Common Error Responses

**404 Not Found:**
```json
{
  "error": "Collection not found",
  "code": "COLLECTION_NOT_FOUND"
}
```

**403 Forbidden:**
```json
{
  "error": "You do not have permission to access this collection",
  "code": "FORBIDDEN"
}
```

**409 Conflict:**
```json
{
  "error": "Topic name already exists",
  "code": "DUPLICATE_TOPIC_NAME"
}
```

**400 Bad Request:**
```json
{
  "error": "Invalid topic_id",
  "code": "INVALID_TOPIC_ID"
}
```

---

## 2.10 Performance Considerations

### Caching Strategy
- Cache topic hierarchy (rarely changes)
- Invalidate cache on topic create/update/delete
- Use Redis or in-memory cache

### Query Optimization
- Eager load relationships when fetching collections with jobs
- Use pagination for job listings
- Add database indexes (already in Phase 1)

### Rate Limiting
- Standard rate limits apply to all endpoints
- No special limits needed for this phase

---

## Deliverables

- [ ] Topic CRUD endpoints (admin-only)
- [ ] Collection CRUD endpoints (user-owned)
- [ ] Job topic assignment endpoints
- [ ] Job collection assignment endpoints
- [ ] Enhanced job listing filters
- [ ] Enhanced search filters
- [ ] Upload endpoint enhancement
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Integration tests for all endpoints
- [ ] Authorization middleware tests

---

## Success Criteria

- All endpoints properly authenticated and authorized
- CRUD operations work for topics and collections
- Job assignments create proper database records
- Filtering and search return correct results
- API documentation is complete and accurate
- All tests passing (>90% coverage)
- No breaking changes to existing API

---

**Estimated Effort**: 4-5 days
**Dependencies**: Phase 1 (Database & Models)
**Next Phase**: Phase 3 - AI Integration
