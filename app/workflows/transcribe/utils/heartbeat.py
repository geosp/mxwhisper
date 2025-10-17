"""
Heartbeat utilities for Temporal activities.

Provides three strategies for sending heartbeats to prevent activity timeouts:
1. HeartbeatPacemaker - Context manager for automatic periodic heartbeats
2. heartbeat_pacemaker - Decorator for activity-wide heartbeats
3. ProgressTracker - Progress-based heartbeats
"""

import asyncio
import functools
import logging
from typing import Callable, Optional
from temporalio import activity

logger = logging.getLogger(__name__)


class HeartbeatPacemaker:
    """
    Context manager that sends automatic periodic heartbeats.

    Usage:
        async with HeartbeatPacemaker("Processing data", interval=5):
            await long_running_task()
    """

    def __init__(self, message: str = "Activity running", interval: int = 5):
        """
        Initialize heartbeat pacemaker.

        Args:
            message: Message to include with heartbeat
            interval: Seconds between heartbeats
        """
        self.message = message
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = False

    async def _heartbeat_loop(self):
        """Background task that sends periodic heartbeats."""
        while not self._stop:
            try:
                activity.heartbeat(self.message)
                logger.debug(f"Heartbeat sent: {self.message}")
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                await asyncio.sleep(self.interval)

    async def __aenter__(self):
        """Start heartbeat pacemaker."""
        activity.heartbeat(f"{self.message} - started")
        self._task = asyncio.create_task(self._heartbeat_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop heartbeat pacemaker."""
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Send final heartbeat with status
        if exc_type is None:
            activity.heartbeat(f"{self.message} - completed")
        else:
            activity.heartbeat(f"{self.message} - failed: {exc_type.__name__}")


def heartbeat_pacemaker(interval: int = 5, message: str = "Processing"):
    """
    Decorator that adds automatic heartbeats to an activity.

    Usage:
        @heartbeat_pacemaker(interval=5, message="Transcribing")
        async def my_activity(job_id: int):
            await long_task()

    Args:
        interval: Seconds between heartbeats
        message: Message to include with heartbeat
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with HeartbeatPacemaker(message, interval):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


class ProgressTracker:
    """
    Track progress and send heartbeats on significant updates.

    Usage:
        progress = ProgressTracker(total=100, job_id=123)
        for i in range(100):
            await do_work()
            progress.update(1)  # Sends heartbeat every 5% change
    """

    def __init__(
        self,
        total: int,
        job_id: Optional[int] = None,
        heartbeat_interval_pct: int = 5
    ):
        """
        Initialize progress tracker.

        Args:
            total: Total units of work
            job_id: Optional job ID for logging
            heartbeat_interval_pct: Send heartbeat every N% change (default: 5%)
        """
        self.total = total
        self.current = 0
        self.job_id = job_id
        self.heartbeat_interval_pct = heartbeat_interval_pct
        self.last_heartbeat_progress = 0

        # Send initial heartbeat
        activity.heartbeat("Progress: 0%")

    def update(self, increment: int = 1, message: Optional[str] = None):
        """
        Update progress and send heartbeat if significant change.

        Args:
            increment: How many units of work completed
            message: Optional custom message (overrides default)
        """
        self.current = min(self.current + increment, self.total)
        progress_pct = int((self.current / self.total) * 100) if self.total > 0 else 0

        # Send heartbeat on significant progress change or completion
        should_heartbeat = (
            progress_pct >= self.last_heartbeat_progress + self.heartbeat_interval_pct
            or progress_pct == 100
        )

        if should_heartbeat:
            self.last_heartbeat_progress = progress_pct
            msg = message or f"Progress: {progress_pct}%"

            if self.job_id:
                msg = f"Job {self.job_id} - {msg}"

            activity.heartbeat(msg)
            logger.debug(msg)

    def set_total(self, new_total: int):
        """Update total units of work (useful when total is discovered mid-process)."""
        self.total = new_total

    @property
    def progress_pct(self) -> int:
        """Get current progress percentage."""
        return int((self.current / self.total) * 100) if self.total > 0 else 0

    @property
    def is_complete(self) -> bool:
        """Check if progress is complete."""
        return self.current >= self.total
