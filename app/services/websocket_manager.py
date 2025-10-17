import json
import logging
from typing import Dict

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Store active WebSocket connections per job_id
active_connections: Dict[int, WebSocket] = {}

async def send_job_update(job_id: int, status: str, transcript: str = None, progress: int = None, error: str = None):
    """Send real-time update to connected WebSocket clients for a job."""
    logger.debug("Attempting to send job update", extra={
        "job_id": job_id,
        "status": status,
        "has_transcript": transcript is not None,
        "progress": progress,
        "has_error": error is not None
    })
    
    if job_id in active_connections:
        websocket = active_connections[job_id]
        try:
            update_data = {"status": status}
            if transcript:
                update_data["transcript"] = transcript
            if progress is not None:
                update_data["progress"] = progress
            if error:
                update_data["error"] = error
                
            await websocket.send_text(json.dumps(update_data))
            logger.debug("Job update sent successfully", extra={
                "job_id": job_id,
                "status": status,
                "progress": progress
            })
        except Exception as e:
            logger.warning("Failed to send WebSocket update, removing connection", extra={
                "job_id": job_id,
                "error": str(e)
            })
            # Connection might be closed, remove it
            del active_connections[job_id]
    else:
        logger.debug("No active WebSocket connection for job", extra={"job_id": job_id})