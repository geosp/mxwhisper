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

def generate_srt(segments):
    """Generate SRT format from Whisper segments."""
    srt_lines = []
    for i, segment in enumerate(segments, 1):
        start_time = format_timestamp(segment['start'])
        end_time = format_timestamp(segment['end'])
        text = segment['text'].strip()
        
        srt_lines.append(str(i))
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(text)
        srt_lines.append("")  # Empty line between entries
    
    return "\n".join(srt_lines)

def format_timestamp(seconds):
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
