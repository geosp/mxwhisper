from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.data import get_db, Role, User, async_session, Job
from app.auth import verify_token
from app.config import settings
from app.logging_config import setup_logging
from app.services import JobService, UserService, create_user_in_authentik_and_db, update_user, delete_user
from app.services.websocket_manager import active_connections, send_job_update
from app.services.embedding_service import generate_embedding
from app.utils.srt import generate_srt
from app.routers import topics_router, collections_router, audio_files_router, transcriptions_router

# Setup logging
setup_logging(level="INFO", format_type="text", log_file="logs/mxwhisper.log")

# Create logger for this module
logger = logging.getLogger(__name__)

class CreateUserRequest(BaseModel):
    email: str
    name: str
    preferred_username: str
    password: str
    role: str = "user"

class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    preferred_username: Optional[str] = None
    role: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

app = FastAPI(title="MxWhisper API")

# Initialize roles on startup
@app.on_event("startup")
async def startup_event():
    logger.info("Starting MxWhisper API server")
    async with async_session() as db:
        await UserService.initialize_roles(db)
    logger.info("MxWhisper API server startup complete")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
)

# Include routers for Phase 2 API endpoints
app.include_router(topics_router)
app.include_router(collections_router)

# Include routers for Phase 4 API endpoints
app.include_router(audio_files_router)
app.include_router(transcriptions_router)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_token)):
    logger.info("File upload request received", extra={
        "file_filename": file.filename,
        "content_type": file.content_type,
        "file_size": file.size,
        "user_id": token_payload.get("sub")
    })
    
    # Check file size
    if file.size and file.size > settings.max_file_size:
        logger.warning("File upload rejected - too large", extra={
            "file_filename": file.filename,
            "file_size": file.size,
            "max_size": settings.max_file_size
        })
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.max_file_size} bytes)")

    # Read file content
    content = await file.read()
    logger.debug("File content read successfully", extra={
        "file_filename": file.filename,
        "content_length": len(content)
    })

    # Get user ID from token
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")

    # Create job with user association
    job = await JobService.create_job(db, file.filename, content, token_payload)
    logger.info("Job created successfully", extra={
        "job_id": job.id,
        "file_filename": job.filename,
        "status": job.status,
        "user_id": token_payload.get("sub")
    })

    # Send initial status update
    await send_job_update(job.id, job.status)

    # Trigger workflow
    await JobService.trigger_workflow(job.id)

    logger.info("File upload completed", extra={
        "job_id": job.id,
        "file_filename": file.filename
    })
    return {"job_id": job.id, "message": "File uploaded and transcription started"}

@app.get("/job/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info("Job status request received", extra={"job_id": job_id})
    
    job = await JobService.get_job(db, job_id)
    if not job:
        logger.warning("Job not found", extra={"job_id": job_id})
        raise HTTPException(status_code=404, detail="Job not found")

    logger.debug("Job status retrieved", extra={
        "job_id": job.id,
        "status": job.status,
        "file_filename": job.filename
    })
    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "transcript": job.transcript
    }

@app.get("/jobs/{job_id}/download")
async def download_transcript(job_id: int, format: str = "txt", db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_token)):
    job = await JobService.get_job(db, job_id)
    if not job or job.status != "completed":
        raise HTTPException(status_code=404, detail="Transcript not available")

    if format.lower() == "srt":
        # Generate SRT format from segments
        if not job.segments:
            raise HTTPException(status_code=404, detail="SRT format not available - no segments data")
        
        import json
        segments = json.loads(job.segments)
        srt_content = generate_srt(segments)
        
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=srt_content, media_type="text/plain")
    else:
        # Return plain text response (default)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=job.transcript, media_type="text/plain")

@app.get("/user/jobs")
async def get_user_jobs(db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_token)):
    """Get all jobs for the authenticated user."""
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")

    jobs = await JobService.get_user_jobs(db, user_id)
    return [
        {
            "id": job.id,
            "filename": job.filename,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        for job in jobs
    ]

@app.post("/search")
async def semantic_search(
    search_request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """
    Semantic search across transcript chunks using vector similarity.

    This endpoint searches semantically meaningful chunks of transcripts,
    providing precise matches with topic summaries and timestamps.

    Benefits of chunk-based search:
    - More relevant results (searches individual topics, not entire transcripts)
    - Navigate directly to the relevant part of the audio
    - See what each chunk is about via topic summaries

    Example queries:
    - Query: "biblical teachings" will find chunks specifically about the Bible
    - Query: "Jesus Christ" will find chunks discussing Jesus
    - Query: "God's anointed one" will find chunks about the Messiah
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")

    logger.info("Semantic search request", extra={
        "user_id": user_id,
        "query": search_request.query,
        "limit": search_request.limit
    })

    # Generate embedding for the search query
    query_embedding = generate_embedding(search_request.query)

    # Perform vector similarity search on chunks
    # Using cosine distance (1 - cosine similarity)
    from sqlalchemy import select, text

    query = text("""
        SELECT
            job_chunks.id as chunk_id,
            job_chunks.job_id,
            job_chunks.chunk_index,
            job_chunks.text as matched_text,
            job_chunks.topic_summary,
            job_chunks.keywords,
            job_chunks.start_time,
            job_chunks.end_time,
            jobs.filename,
            jobs.created_at,
            (1 - (job_chunks.embedding <=> :query_embedding)) as similarity
        FROM job_chunks
        JOIN jobs ON job_chunks.job_id = jobs.id
        WHERE
            jobs.status = 'completed'
            AND job_chunks.embedding IS NOT NULL
            AND jobs.user_id = :user_id
        ORDER BY job_chunks.embedding <=> :query_embedding
        LIMIT :limit
    """)

    result = await db.execute(
        query,
        {
            "query_embedding": str(query_embedding),
            "user_id": user_id,
            "limit": search_request.limit
        }
    )

    results = []
    for row in result:
        # Build result with chunk text, topic summary, and timestamp
        result_item = {
            "chunk_id": row.chunk_id,
            "job_id": row.job_id,
            "chunk_index": row.chunk_index,
            "filename": row.filename,
            "matched_text": row.matched_text,
            "topic_summary": row.topic_summary,
            "keywords": row.keywords,
            "timestamp": {
                "start": row.start_time,
                "end": row.end_time
            } if row.start_time is not None and row.end_time is not None else None,
            "similarity": float(row.similarity),
            "created_at": row.created_at,
        }
        results.append(result_item)

    logger.info("Semantic search completed", extra={
        "user_id": user_id,
        "query": search_request.query,
        "results_count": len(results)
    })

    return {
        "query": search_request.query,
        "results": results
    }

@app.get("/admin/jobs")
async def get_all_jobs(db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_token)):
    """Admin endpoint to get all jobs."""
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    jobs = await JobService.get_all_jobs(db, user_id)
    return [
        {
            "id": job.id,
            "filename": job.filename,
            "status": job.status,
            "user_id": job.user_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        for job in jobs
    ]

@app.get("/admin/users")
async def get_all_users(db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_token)):
    """Admin endpoint to get all users."""
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from sqlalchemy import select
    result = await db.execute(
        select(User, Role.name.label("role_name"))
        .join(Role, User.role_id == Role.id)
    )
    
    users = []
    for user, role_name in result:
        users.append({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "preferred_username": user.preferred_username,
            "role": role_name,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        })
    
    return users

@app.post("/admin/users")
async def create_user(
    user_data: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """Admin endpoint to create a new user in both Authentik and the local database."""
    user_id = token_payload.get("sub")
    if not user_id or not await UserService.is_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        user = await create_user_in_authentik_and_db(
            db=db,
            email=user_data.email,
            name=user_data.name,
            preferred_username=user_data.preferred_username,
            password=user_data.password,
            role=user_data.role
        )
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "preferred_username": user.preferred_username,
            "role": user.role.name if user.role else user_data.role,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")

@app.put("/admin/users/{user_id}")
async def update_user_endpoint(
    user_id: str,
    user_data: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """Admin endpoint to update user information."""
    user_id_from_token = token_payload.get("sub")
    if not user_id_from_token or not await UserService.is_admin(db, user_id_from_token):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        user = await update_user(db, user_id, user_data.dict(exclude_unset=True))
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "preferred_username": user.preferred_username,
            "role": user.role.name if user.role else None,
            "updated_at": user.updated_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update user: {str(e)}")

@app.delete("/admin/users/{user_id}")
async def delete_user_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    """Admin endpoint to delete a user."""
    user_id_from_token = token_payload.get("sub")
    if not user_id_from_token or not await UserService.is_admin(db, user_id_from_token):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        await delete_user(db, user_id)
        return {"message": f"User {user_id} deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete user: {str(e)}")

@app.websocket("/ws/jobs/{job_id}")
async def job_updates_websocket(websocket: WebSocket, job_id: int):
    """WebSocket endpoint for real-time job status updates."""
    logger.info("WebSocket connection established", extra={"job_id": job_id})
    
    await websocket.accept()
    logger.debug("WebSocket connection accepted", extra={"job_id": job_id})
    
    # Add to active connections
    active_connections[job_id] = websocket
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            logger.debug("WebSocket message received", extra={
                "job_id": job_id,
                "message": data
            })
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed", extra={"job_id": job_id})
    except Exception as e:
        logger.error("WebSocket error occurred", extra={
            "job_id": job_id,
            "error": str(e)
        })
    finally:
        # Remove from active connections
        if job_id in active_connections:
            del active_connections[job_id]
            logger.debug("WebSocket connection removed from active connections", extra={"job_id": job_id})
