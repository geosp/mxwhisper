# Phase 4: MCP Server (Knowledge Base Interface)

## Overview
Build an MCP server that enables users to interact with their MxWhisper knowledge base through AI assistants (Claude Desktop, Cursor, etc.) using the **mcp-weather core pattern** with automatic feature discovery.

## Goals
- Create MCP server using mcp-weather as dependency
- Implement MCP tools for knowledge base interaction
- Provide dual interface (MCP + REST API)
- Enable natural language knowledge base queries
- Support upload, search, organization, and retrieval

---

## Architecture

### Using mcp-weather Core Pattern

```
mcp_mxwhisper/
├── __init__.py              # Package metadata
├── config.py                # Configuration management
├── mxwhisper_client.py      # MxWhisper API client (business logic)
├── service.py               # MCP service wrapper (with feature discovery)
├── server.py                # Server implementation
├── features/                # Feature modules (AUTO-DISCOVERED)
│   ├── __init__.py
│   ├── search/              # Search knowledge base
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── tool.py          # MCP tool definition
│   │   └── routes.py        # REST API endpoints
│   ├── topics/              # Topic management
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── tool.py
│   │   └── routes.py
│   ├── collections/         # Collection management
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── tool.py
│   │   └── routes.py
│   ├── jobs/                # Job retrieval
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── tool.py
│   │   └── routes.py
│   ├── upload/              # Upload audio
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── tool.py
│   │   └── routes.py
│   └── transcripts/         # Transcript retrieval
│       ├── __init__.py
│       ├── models.py
│       ├── tool.py
│       └── routes.py
└── shared/                  # Shared models and utilities
    ├── __init__.py
    └── models.py            # Base models, error types
```

---

## 4.1 Configuration (config.py)

```python
from pydantic import BaseModel, Field
from core.config import BaseServerConfig

class MxWhisperAPIConfig(BaseModel):
    """MxWhisper API configuration."""
    base_url: str = Field(
        default="http://localhost:8000",
        description="MxWhisper API base URL"
    )
    api_key: str = Field(
        ...,
        description="MxWhisper API authentication key"
    )
    timeout: int = Field(
        default=300,
        description="Request timeout in seconds"
    )

class AppConfig(BaseModel):
    """Application configuration."""
    server: BaseServerConfig
    mxwhisper: MxWhisperAPIConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        return cls(
            server=BaseServerConfig(
                name=os.getenv("MCP_SERVER_NAME", "mxwhisper"),
                version=os.getenv("MCP_SERVER_VERSION", "1.0.0"),
                transport=os.getenv("MCP_TRANSPORT", "stdio"),
                host=os.getenv("MCP_HOST", "0.0.0.0"),
                port=int(os.getenv("MCP_PORT", "3000")),
                mcp_only=os.getenv("MCP_ONLY", "true").lower() == "true",
            ),
            mxwhisper=MxWhisperAPIConfig(
                base_url=os.getenv("MXWHISPER_API_URL", "http://localhost:8000"),
                api_key=os.getenv("MXWHISPER_API_KEY", ""),
                timeout=int(os.getenv("MXWHISPER_TIMEOUT", "300")),
            )
        )
```

---

## 4.2 MxWhisper API Client (mxwhisper_client.py)

```python
import httpx
from typing import List, Optional, Dict, Any
from .config import MxWhisperAPIConfig
from .shared.models import (
    SearchResult, Topic, Collection, Job, Transcript, UploadResponse
)

class MxWhisperClient:
    """
    Client for MxWhisper API.
    Pure business logic, independent of MCP/REST.
    """

    def __init__(self, config: MxWhisperAPIConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {config.api_key}"}
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    # Search
    async def search(
        self,
        query: str,
        topic_ids: Optional[List[int]] = None,
        collection_ids: Optional[List[int]] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """Search knowledge base."""
        params = {
            "q": query,
            "limit": limit
        }
        if topic_ids:
            params["topic_ids"] = ",".join(map(str, topic_ids))
        if collection_ids:
            params["collection_ids"] = ",".join(map(str, collection_ids))

        response = await self.client.get("/search", params=params)
        response.raise_for_status()
        data = response.json()
        return [SearchResult(**item) for item in data.get("results", [])]

    # Topics
    async def list_topics(self) -> List[Topic]:
        """Get all topics (hierarchical)."""
        response = await self.client.get("/topics")
        response.raise_for_status()
        data = response.json()
        return self._build_topic_hierarchy(data.get("topics", []))

    def _build_topic_hierarchy(self, topics: List[dict]) -> List[Topic]:
        """Build hierarchical topic structure."""
        # Convert flat list to hierarchy
        topic_map = {t["id"]: Topic(**t) for t in topics}
        root_topics = []
        for topic in topic_map.values():
            if topic.parent_id:
                parent = topic_map.get(topic.parent_id)
                if parent:
                    parent.children.append(topic)
            else:
                root_topics.append(topic)
        return root_topics

    async def get_jobs_by_topic(
        self,
        topic_id: int,
        include_children: bool = False
    ) -> List[Job]:
        """Get all jobs in a topic."""
        params = {"topic_id": topic_id}
        if include_children:
            params["include_children"] = "true"

        response = await self.client.get("/user/jobs", params=params)
        response.raise_for_status()
        data = response.json()
        return [Job(**item) for item in data.get("jobs", [])]

    # Collections
    async def list_collections(self) -> List[Collection]:
        """Get user's collections."""
        response = await self.client.get("/collections")
        response.raise_for_status()
        data = response.json()
        return [Collection(**item) for item in data.get("collections", [])]

    async def get_collection(self, collection_id: int) -> Collection:
        """Get collection details with jobs."""
        response = await self.client.get(f"/collections/{collection_id}")
        response.raise_for_status()
        return Collection(**response.json())

    async def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        collection_type: Optional[str] = None
    ) -> Collection:
        """Create a new collection."""
        payload = {"name": name}
        if description:
            payload["description"] = description
        if collection_type:
            payload["collection_type"] = collection_type

        response = await self.client.post("/collections", json=payload)
        response.raise_for_status()
        return Collection(**response.json())

    async def add_job_to_collection(
        self,
        job_id: int,
        collection_id: int,
        position: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add job to collection."""
        payload = {"collection_id": collection_id}
        if position is not None:
            payload["position"] = position

        response = await self.client.post(
            f"/jobs/{job_id}/collections",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # Jobs
    async def get_job(self, job_id: int) -> Job:
        """Get job details."""
        response = await self.client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        return Job(**response.json())

    async def get_transcript(
        self,
        job_id: int,
        include_chunks: bool = False
    ) -> Transcript:
        """Get full transcript."""
        params = {}
        if include_chunks:
            params["include_chunks"] = "true"

        response = await self.client.get(
            f"/jobs/{job_id}/transcript",
            params=params
        )
        response.raise_for_status()
        return Transcript(**response.json())

    async def list_jobs(
        self,
        topic_id: Optional[int] = None,
        collection_id: Optional[int] = None,
        needs_review: Optional[bool] = None,
        limit: int = 50
    ) -> List[Job]:
        """List jobs with filters."""
        params = {"limit": limit}
        if topic_id:
            params["topic_id"] = topic_id
        if collection_id:
            params["collection_id"] = collection_id
        if needs_review is not None:
            params["needs_review"] = str(needs_review).lower()

        response = await self.client.get("/user/jobs", params=params)
        response.raise_for_status()
        data = response.json()
        return [Job(**item) for item in data.get("jobs", [])]

    # Upload
    async def upload_audio(
        self,
        file_path: str,
        title: Optional[str] = None,
        topic_ids: Optional[List[int]] = None,
        collection_id: Optional[int] = None,
        position: Optional[int] = None
    ) -> UploadResponse:
        """Upload audio file for transcription."""
        files = {"file": open(file_path, "rb")}
        data = {}
        if title:
            data["title"] = title
        if topic_ids:
            data["topic_ids"] = ",".join(map(str, topic_ids))
        if collection_id:
            data["collection_id"] = collection_id
        if position is not None:
            data["position"] = position

        response = await self.client.post(
            "/upload",
            files=files,
            data=data
        )
        response.raise_for_status()
        return UploadResponse(**response.json())
```

---

## 4.3 Feature: Search (features/search/)

### features/search/models.py
```python
from pydantic import BaseModel, Field
from typing import Optional, List

class SearchInput(BaseModel):
    """Input for search tool."""
    query: str = Field(..., description="Search query")
    topic_ids: Optional[List[int]] = Field(
        None,
        description="Filter by topic IDs"
    )
    collection_ids: Optional[List[int]] = Field(
        None,
        description="Filter by collection IDs"
    )
    limit: int = Field(
        default=10,
        description="Maximum number of results"
    )

class SearchOutput(BaseModel):
    """Output from search tool."""
    results: List[dict]
    total: int
```

### features/search/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient
from .models import SearchInput, SearchOutput

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register search MCP tool (auto-discovered)."""

    @mcp.tool()
    async def search_knowledge_base(
        query: str,
        topic_ids: list[int] | None = None,
        collection_ids: list[int] | None = None,
        limit: int = 10
    ) -> dict:
        """
        Search through transcribed audio content in the knowledge base.

        Use this tool to find relevant transcripts based on natural language queries.
        You can filter by topics or collections to narrow results.

        Args:
            query: Natural language search query
            topic_ids: Optional list of topic IDs to filter by
            collection_ids: Optional list of collection IDs to filter by
            limit: Maximum number of results to return (default: 10)

        Returns:
            Dictionary with search results and metadata
        """
        results = await client.search(
            query=query,
            topic_ids=topic_ids,
            collection_ids=collection_ids,
            limit=limit
        )

        return {
            "results": [
                {
                    "job_id": r.job_id,
                    "title": r.title,
                    "excerpt": r.excerpt,
                    "relevance_score": r.score,
                    "topics": r.topics,
                    "created_at": r.created_at.isoformat()
                }
                for r in results
            ],
            "total": len(results),
            "query": query
        }
```

### features/search/routes.py
```python
from fastapi import APIRouter, Depends
from ..mxwhisper_client import MxWhisperClient
from .models import SearchInput, SearchOutput

def create_router(client: MxWhisperClient) -> APIRouter:
    """Create REST API router for search (auto-discovered)."""
    router = APIRouter(prefix="/search", tags=["Search"])

    @router.post("", response_model=SearchOutput)
    async def search_endpoint(input: SearchInput):
        """Search knowledge base via REST API."""
        results = await client.search(
            query=input.query,
            topic_ids=input.topic_ids,
            collection_ids=input.collection_ids,
            limit=input.limit
        )
        return SearchOutput(
            results=[r.dict() for r in results],
            total=len(results)
        )

    return router
```

---

## 4.4 Feature: Topics (features/topics/)

### features/topics/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register topic management tools."""

    @mcp.tool()
    async def list_topics() -> dict:
        """
        Get all available topics in hierarchical structure.

        Use this to understand what categories of content are available
        in the knowledge base.

        Returns:
            Hierarchical list of topics with their children
        """
        topics = await client.list_topics()

        def topic_to_dict(topic):
            return {
                "id": topic.id,
                "name": topic.name,
                "description": topic.description,
                "children": [topic_to_dict(c) for c in topic.children]
            }

        return {
            "topics": [topic_to_dict(t) for t in topics]
        }

    @mcp.tool()
    async def get_jobs_by_topic(
        topic_id: int,
        include_children: bool = False
    ) -> dict:
        """
        Get all transcripts in a specific topic.

        Args:
            topic_id: The topic ID to retrieve jobs from
            include_children: Include jobs from child topics (default: False)

        Returns:
            List of jobs in the topic
        """
        jobs = await client.get_jobs_by_topic(topic_id, include_children)

        return {
            "topic_id": topic_id,
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "created_at": j.created_at.isoformat(),
                    "status": j.status
                }
                for j in jobs
            ],
            "total": len(jobs)
        }
```

---

## 4.5 Feature: Collections (features/collections/)

### features/collections/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register collection management tools."""

    @mcp.tool()
    async def list_collections() -> dict:
        """
        Get all user's collections (series, books, courses, etc.).

        Returns:
            List of collections with metadata
        """
        collections = await client.list_collections()

        return {
            "collections": [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "collection_type": c.collection_type,
                    "job_count": c.job_count,
                    "is_public": c.is_public
                }
                for c in collections
            ]
        }

    @mcp.tool()
    async def get_collection(collection_id: int) -> dict:
        """
        Get collection details with all jobs in order.

        Args:
            collection_id: The collection ID to retrieve

        Returns:
            Collection with ordered list of jobs
        """
        collection = await client.get_collection(collection_id)

        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "collection_type": collection.collection_type,
            "jobs": [
                {
                    "job_id": j.job_id,
                    "position": j.position,
                    "title": j.title,
                    "created_at": j.created_at.isoformat()
                }
                for j in sorted(collection.jobs, key=lambda x: x.position or 0)
            ]
        }

    @mcp.tool()
    async def create_collection(
        name: str,
        description: str | None = None,
        collection_type: str | None = None
    ) -> dict:
        """
        Create a new collection.

        Use this to organize related transcripts (e.g., sermon series,
        book chapters, course modules).

        Args:
            name: Collection name
            description: Optional description
            collection_type: Type (e.g., 'series', 'book', 'course')

        Returns:
            Created collection details
        """
        collection = await client.create_collection(
            name=name,
            description=description,
            collection_type=collection_type
        )

        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "collection_type": collection.collection_type,
            "created_at": collection.created_at.isoformat()
        }

    @mcp.tool()
    async def add_job_to_collection(
        job_id: int,
        collection_id: int,
        position: int | None = None
    ) -> dict:
        """
        Add a transcript to a collection.

        Args:
            job_id: The transcript/job ID to add
            collection_id: The collection to add to
            position: Optional position in collection (for ordering)

        Returns:
            Assignment confirmation
        """
        result = await client.add_job_to_collection(
            job_id=job_id,
            collection_id=collection_id,
            position=position
        )

        return {
            "success": True,
            "job_id": job_id,
            "collection_id": collection_id,
            "position": position,
            "message": "Job added to collection successfully"
        }
```

---

## 4.6 Feature: Jobs (features/jobs/)

### features/jobs/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register job retrieval tools."""

    @mcp.tool()
    async def get_job(job_id: int) -> dict:
        """
        Get details about a specific transcription job.

        Args:
            job_id: The job ID to retrieve

        Returns:
            Job details including status, topics, collections
        """
        job = await client.get_job(job_id)

        return {
            "id": job.id,
            "title": job.title,
            "status": job.status,
            "duration": job.duration,
            "topics": [
                {"id": t.id, "name": t.name}
                for t in job.topics
            ],
            "collections": [
                {"id": c.id, "name": c.name}
                for c in job.collections
            ],
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        }

    @mcp.tool()
    async def list_jobs(
        topic_id: int | None = None,
        collection_id: int | None = None,
        needs_review: bool | None = None,
        limit: int = 50
    ) -> dict:
        """
        List transcription jobs with optional filters.

        Args:
            topic_id: Filter by topic
            collection_id: Filter by collection
            needs_review: Show jobs needing topic review
            limit: Maximum results (default: 50)

        Returns:
            List of jobs matching filters
        """
        jobs = await client.list_jobs(
            topic_id=topic_id,
            collection_id=collection_id,
            needs_review=needs_review,
            limit=limit
        )

        return {
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "status": j.status,
                    "created_at": j.created_at.isoformat()
                }
                for j in jobs
            ],
            "total": len(jobs)
        }
```

---

## 4.7 Feature: Transcripts (features/transcripts/)

### features/transcripts/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register transcript retrieval tools."""

    @mcp.tool()
    async def get_transcript(
        job_id: int,
        include_chunks: bool = False
    ) -> dict:
        """
        Get the full transcript of a transcription job.

        Use this to read the actual transcribed content.

        Args:
            job_id: The job ID to get transcript for
            include_chunks: Include individual chunks (default: False)

        Returns:
            Full transcript text and metadata
        """
        transcript = await client.get_transcript(job_id, include_chunks)

        result = {
            "job_id": job_id,
            "text": transcript.text,
            "word_count": len(transcript.text.split()),
            "duration": transcript.duration
        }

        if include_chunks:
            result["chunks"] = [
                {
                    "index": c.index,
                    "text": c.text,
                    "start_time": c.start_time,
                    "end_time": c.end_time,
                    "topic_summary": c.topic_summary
                }
                for c in transcript.chunks
            ]

        return result
```

---

## 4.8 Feature: Upload (features/upload/)

### features/upload/tool.py
```python
from fastmcp import FastMCP
from ..mxwhisper_client import MxWhisperClient

def register_tool(mcp: FastMCP, client: MxWhisperClient):
    """Register upload tools."""

    @mcp.tool()
    async def upload_audio(
        file_path: str,
        title: str | None = None,
        topic_ids: list[int] | None = None,
        collection_id: int | None = None,
        position: int | None = None
    ) -> dict:
        """
        Upload an audio file for transcription.

        Args:
            file_path: Path to audio file
            title: Optional custom title (defaults to filename)
            topic_ids: Optional list of topic IDs to assign
            collection_id: Optional collection to add to
            position: Optional position in collection

        Returns:
            Upload confirmation with job ID
        """
        response = await client.upload_audio(
            file_path=file_path,
            title=title,
            topic_ids=topic_ids,
            collection_id=collection_id,
            position=position
        )

        return {
            "success": True,
            "job_id": response.job_id,
            "status": response.status,
            "message": "Audio uploaded successfully. Transcription in progress.",
            "estimated_completion": response.estimated_completion
        }
```

---

## 4.9 MCP Service (service.py)

```python
from core.server import BaseService
from fastmcp import FastMCP
from .config import AppConfig
from .mxwhisper_client import MxWhisperClient
import importlib
import pkgutil

class MxWhisperMCPService(BaseService):
    """
    MCP service for MxWhisper knowledge base.
    Uses automatic feature discovery from features/ directory.
    """

    def __init__(self, config: AppConfig):
        super().__init__(config.server)
        self.config = config
        self.client = MxWhisperClient(config.mxwhisper)

    async def initialize(self):
        """Initialize service (called on startup)."""
        await super().initialize()
        # Test API connection
        try:
            await self.client.list_topics()
        except Exception as e:
            self.logger.error(f"Failed to connect to MxWhisper API: {e}")
            raise

    async def shutdown(self):
        """Shutdown service (called on cleanup)."""
        await self.client.close()
        await super().shutdown()

    def register_mcp_tools(self, mcp: FastMCP) -> None:
        """
        Register MCP tools via automatic feature discovery.
        Discovers all features/* directories and calls their register_tool().
        """
        from . import features

        # Auto-discover features
        feature_modules = pkgutil.iter_modules(
            features.__path__,
            prefix=f"{features.__name__}."
        )

        for _, name, _ in feature_modules:
            try:
                module = importlib.import_module(f"{name}.tool")
                if hasattr(module, "register_tool"):
                    module.register_tool(mcp, self.client)
                    self.logger.info(f"Registered MCP tools from {name}")
            except Exception as e:
                self.logger.warning(f"Could not load MCP tools from {name}: {e}")
```

---

## 4.10 Server Implementation (server.py)

```python
from core.server import BaseMCPServer
from fastapi import APIRouter
from .config import AppConfig
from .service import MxWhisperMCPService
import importlib
import pkgutil

class MxWhisperMCPServer(BaseMCPServer):
    """MCP server for MxWhisper knowledge base."""

    def __init__(self):
        self.config = AppConfig.from_env()
        self.service = MxWhisperMCPService(self.config)
        super().__init__(self.config.server, self.service)

    @property
    def service_title(self) -> str:
        return "MxWhisper Knowledge Base"

    @property
    def service_description(self) -> str:
        return (
            "AI-powered knowledge base for transcribed audio content. "
            "Search, organize, and retrieve transcripts with topics and collections."
        )

    def create_router(self) -> APIRouter:
        """
        Create REST API router via automatic feature discovery.
        Discovers all features/* directories and includes their routes.
        """
        router = APIRouter()

        # Auto-discover feature routers
        from . import features

        feature_modules = pkgutil.iter_modules(
            features.__path__,
            prefix=f"{features.__name__}."
        )

        for _, name, _ in feature_modules:
            try:
                module = importlib.import_module(f"{name}.routes")
                if hasattr(module, "create_router"):
                    feature_router = module.create_router(self.service.client)
                    router.include_router(feature_router)
                    self.logger.info(f"Registered REST routes from {name}")
            except Exception as e:
                self.logger.warning(f"Could not load routes from {name}: {e}")

        return router

def main():
    """Entry point for MCP server."""
    server = MxWhisperMCPServer()
    server.run()

if __name__ == "__main__":
    main()
```

---

## 4.11 Shared Models (shared/models.py)

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Topic(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    children: List["Topic"] = []

class Collection(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    collection_type: Optional[str] = None
    job_count: int = 0
    is_public: bool = False
    jobs: List["CollectionJob"] = []
    created_at: datetime

class CollectionJob(BaseModel):
    job_id: int
    position: Optional[int] = None
    title: str
    created_at: datetime

class Job(BaseModel):
    id: int
    title: str
    status: str
    duration: Optional[float] = None
    topics: List[Topic] = []
    collections: List[Collection] = []
    created_at: datetime
    completed_at: Optional[datetime] = None

class SearchResult(BaseModel):
    job_id: int
    title: str
    excerpt: str
    score: float
    topics: List[str] = []
    created_at: datetime

class TranscriptChunk(BaseModel):
    index: int
    text: str
    start_time: float
    end_time: float
    topic_summary: Optional[str] = None

class Transcript(BaseModel):
    job_id: int
    text: str
    duration: float
    chunks: List[TranscriptChunk] = []

class UploadResponse(BaseModel):
    job_id: int
    status: str
    estimated_completion: Optional[datetime] = None
```

---

## 4.12 Configuration Files

### .env.example
```bash
# MCP Server Configuration
MCP_SERVER_NAME=mxwhisper
MCP_SERVER_VERSION=1.0.0
MCP_TRANSPORT=stdio  # or 'http'
MCP_HOST=0.0.0.0
MCP_PORT=3000
MCP_ONLY=true  # Set to false to enable REST API

# MxWhisper API Configuration
MXWHISPER_API_URL=http://localhost:8000
MXWHISPER_API_KEY=your-api-key-here
MXWHISPER_TIMEOUT=300
```

### pyproject.toml
```toml
[project]
name = "mcp-mxwhisper"
version = "1.0.0"
description = "MCP server for MxWhisper knowledge base"
requires-python = ">=3.10"
dependencies = [
    "mcp-weather>=1.0.0",  # Core MCP infrastructure
    "fastmcp>=0.2.0",
    "fastapi>=0.104.0",
    "httpx>=0.25.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
mcp-mxwhisper = "mcp_mxwhisper.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 4.13 Installation & Usage

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/mcp-mxwhisper.git
cd mcp-mxwhisper

# Install dependencies with uv
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your MxWhisper API URL and key
```

### Run in MCP-only Mode (stdio)
```bash
# For Claude Desktop, Cursor, etc.
export MCP_TRANSPORT=stdio
export MCP_ONLY=true

uv run python -m mcp_mxwhisper.server
```

### Run in HTTP Mode (dual interface)
```bash
# MCP + REST API
export MCP_TRANSPORT=http
export MCP_ONLY=false
export MCP_PORT=3000

uv run python -m mcp_mxwhisper.server
```

### Claude Desktop Configuration

**~/.config/claude/claude_desktop_config.json**
```json
{
  "mcpServers": {
    "mxwhisper": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/mcp-mxwhisper",
        "run",
        "python",
        "-m",
        "mcp_mxwhisper.server"
      ],
      "env": {
        "MXWHISPER_API_URL": "http://localhost:8000",
        "MXWHISPER_API_KEY": "your-api-key"
      }
    }
  }
}
```

---

## 4.14 Example User Workflows

### Workflow 1: Research & Discovery
```
User: "Search my knowledge base for all content about Romans chapter 3"

Claude (via MCP):
1. search_knowledge_base(query="Romans chapter 3")
2. Returns 5 relevant transcripts
3. get_transcript(job_id=123) for the most relevant one
4. Presents summary and key points

User: "Show me the full transcript of the first result"

Claude: [Displays full transcript with context]
```

### Workflow 2: Collection Management
```
User: "I'm starting a new sermon series on Romans. Create a collection for it."

Claude (via MCP):
1. create_collection(name="Romans Sermon Series", type="series")
2. Returns collection ID

User: "Add job #123 to this collection as the first sermon"

Claude:
1. add_job_to_collection(job_id=123, collection_id=X, position=1)
2. Confirms addition
```

### Workflow 3: Knowledge Organization
```
User: "What topics do I have the most content in?"

Claude (via MCP):
1. list_topics()
2. get_jobs_by_topic() for each topic
3. Analyzes and presents statistics:
   - Bible Study: 45 transcripts
   - Sermons: 32 transcripts
   - Prayer: 12 transcripts

User: "Show me all my Bible Study content from last month"

Claude: [Filters and displays relevant jobs]
```

### Workflow 4: Content Upload
```
User: "I just recorded a sermon. Upload sermon.mp3 and add it to my Sunday Sermons collection"

Claude (via MCP):
1. upload_audio(file_path="sermon.mp3", collection_id=sunday_sermons)
2. Monitors transcription progress
3. Notifies when complete with AI-suggested topics
```

---

## 4.15 Testing Strategy

### Unit Tests
```python
# tests/test_client.py
async def test_search():
    client = MxWhisperClient(config)
    results = await client.search("Romans 3")
    assert len(results) > 0

# tests/test_tools.py
async def test_search_tool(mcp_client):
    result = await mcp_client.call_tool(
        "search_knowledge_base",
        {"query": "Romans 3"}
    )
    assert result["total"] > 0
```

### Integration Tests
```python
# Test full MCP workflow
async def test_create_collection_workflow():
    # Create collection
    result1 = await mcp.call_tool(
        "create_collection",
        {"name": "Test Series"}
    )
    collection_id = result1["id"]

    # Add job to collection
    result2 = await mcp.call_tool(
        "add_job_to_collection",
        {
            "job_id": 123,
            "collection_id": collection_id
        }
    )
    assert result2["success"] is True
```

---

## Deliverables

- [ ] MCP server implementation using mcp-weather core
- [ ] All 6 feature modules (search, topics, collections, jobs, transcripts, upload)
- [ ] MxWhisperClient (API client layer)
- [ ] Automatic feature discovery system
- [ ] Configuration management
- [ ] Shared models and utilities
- [ ] Installation and setup documentation
- [ ] Claude Desktop integration guide
- [ ] Example workflows and usage guide
- [ ] Unit and integration tests
- [ ] Error handling and validation
- [ ] Logging and monitoring

---

## Success Criteria

- ✅ MCP tools auto-discovered from features/ directory
- ✅ Dual interface (MCP + REST API) working
- ✅ Claude Desktop can interact with knowledge base
- ✅ All CRUD operations functional
- ✅ Search returns relevant results
- ✅ Collections can be created and managed
- ✅ File uploads work end-to-end
- ✅ Error handling is comprehensive
- ✅ Documentation is complete and clear
- ✅ Tests achieve >80% coverage

---

## Next Steps After Phase 4

### Phase 5: Advanced Features (Optional)
- Conversational memory (remember previous queries)
- Cross-transcript analysis (compare multiple transcripts)
- Auto-summarization tools
- Citation extraction
- Speaker identification integration
- Timeline visualization

### Phase 6: UI (Optional)
- Web interface for non-MCP users
- Visual collection management
- Analytics dashboard
- Bulk operations interface

---

**Estimated Effort**: 3-5 days
**Dependencies**: Phase 1-3 (API must be complete)
**Pattern**: mcp-weather core with automatic feature discovery
**Primary Interface**: MCP (stdio/http)
**Secondary Interface**: REST API (optional)
