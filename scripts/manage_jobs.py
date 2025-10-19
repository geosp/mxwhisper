#!/usr/bin/env python3
"""
Manage Jobs

This script provides job management operations.

Commands:
    list                  List all jobs with their status and details
    show <job_id>         Show detailed information about a specific job

Usage:
    uv run python scripts/manage_jobs.py list [--user USERNAME] [--status STATUS]
    uv run python scripts/manage_jobs.py show <job_id> [--format transcript|srt]

Examples:
    # List all jobs
    uv run python scripts/manage_jobs.py list

    # List jobs for a specific user
    uv run python scripts/manage_jobs.py list --user john.doe

    # List jobs with specific status
    uv run python scripts/manage_jobs.py list --status completed

    # Show job details
    uv run python scripts/manage_jobs.py show 123

    # Show job transcript
    uv run python scripts/manage_jobs.py show 123 --format transcript

    # Show job SRT
    uv run python scripts/manage_jobs.py show 123 --format srt
"""

import asyncio
import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.data import Job, JobChunk, User, get_db_session

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def format_timestamp(seconds):
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


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


async def list_jobs(user_filter: str = None, status_filter: str = None):
    """List all jobs with their status and details."""
    db = None
    try:
        db = await get_db_session()

        # Build query
        query = select(Job).options(selectinload(Job.user)).order_by(Job.created_at.desc())

        # Apply filters
        if user_filter:
            # Find user by preferred_username
            user_result = await db.execute(select(User).where(User.preferred_username == user_filter))
            user = user_result.scalar_one_or_none()
            if user:
                query = query.where(Job.user_id == user.id)
            else:
                print(f"❌ User '{user_filter}' not found")
                return

        if status_filter:
            query = query.where(Job.status == status_filter)

        # Execute query
        result = await db.execute(query)
        jobs = result.scalars().all()

        if not jobs:
            if user_filter:
                print(f"No jobs found for user '{user_filter}'")
            elif status_filter:
                print(f"No jobs found with status '{status_filter}'")
            else:
                print("No jobs found in database")
            return

        print("=" * 120)
        print(f"{'Job ID':<8} {'Filename':<30} {'User':<20} {'Status':<12} {'Chunks':<8} {'Created':<20}")
        print("=" * 120)

        for job in jobs:
            # Get chunk count
            chunk_result = await db.execute(select(JobChunk).where(JobChunk.job_id == job.id))
            chunk_count = len(chunk_result.scalars().all())

            # Get username
            username = "N/A"
            if job.user:
                username = job.user.preferred_username or "N/A"

            # Format created date
            created = job.created_at.strftime("%Y-%m-%d %H:%M:%S")

            print(f"{job.id:<8} {job.filename[:28]:<30} {username[:18]:<20} {job.status:<12} {chunk_count:<8} {created:<20}")

        print("=" * 120)
        print(f"Total jobs: {len(jobs)}")

    except Exception as e:
        print(f"❌ Failed to list jobs: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


async def show_job(job_id: int, output_format: str = None):
    """Show detailed information about a specific job."""
    db = None
    try:
        db = await get_db_session()

        # Get job
        result = await db.execute(select(Job).options(selectinload(Job.user)).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            print(f"❌ Job with ID {job_id} not found")
            return

        # Get username
        username = "N/A"
        if job.user:
            username = job.user.preferred_username or "N/A"

        print("=" * 80)
        print(f"Job Details - ID: {job.id}")
        print("=" * 80)
        print(f"Filename: {job.filename}")
        print(f"File Path: {job.file_path}")
        print(f"User: {username}")
        print(f"Status: {job.status}")
        print(f"Created: {job.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Updated: {job.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()

        # Get chunks
        chunk_result = await db.execute(select(JobChunk).where(JobChunk.job_id == job.id).order_by(JobChunk.chunk_index))
        chunks = chunk_result.scalars().all()

        if chunks:
            print(f"Chunks ({len(chunks)}):")
            print("-" * 80)
            for chunk in chunks:
                start_time = f"{chunk.start_time:.1f}s" if chunk.start_time else "N/A"
                end_time = f"{chunk.end_time:.1f}s" if chunk.end_time else "N/A"
                confidence = f"{chunk.confidence:.2f}" if chunk.confidence else "N/A"
                text_preview = chunk.text[:60] + "..." if len(chunk.text) > 60 else chunk.text

                print(f"  {chunk.chunk_index}: [{start_time}-{end_time}] {confidence} - {text_preview}")
            print()

        # Handle output format
        if output_format == "transcript":
            if job.transcript:
                print("Transcript:")
                print("-" * 80)
                print(job.transcript)
            else:
                print("❌ No transcript available for this job")

        elif output_format == "srt":
            if job.segments:
                try:
                    segments = json.loads(job.segments)
                    srt_content = generate_srt(segments)
                    print("SRT Content:")
                    print("-" * 80)
                    print(srt_content)
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse segments data: {e}")
            else:
                print("❌ No segments data available for SRT generation")

    except Exception as e:
        print(f"❌ Failed to show job: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            await db.close()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs with their status')
    list_parser.add_argument('--user', help='Filter by username')
    list_parser.add_argument('--status', help='Filter by job status (pending, processing, completed, failed)')

    # Show command
    show_parser = subparsers.add_parser('show', help='Show detailed information about a job')
    show_parser.add_argument('job_id', type=int, help='Job ID to show')
    show_parser.add_argument('--format', choices=['transcript', 'srt'],
                           help='Output format (transcript or srt)')

    return parser.parse_args()


async def main():
    """Main script execution."""
    args = parse_arguments()

    if args.command == 'list':
        await list_jobs(args.user if hasattr(args, 'user') else None,
                       args.status if hasattr(args, 'status') else None)
    elif args.command == 'show':
        await show_job(args.job_id, args.format if hasattr(args, 'format') else None)


if __name__ == "__main__":
    asyncio.run(main())
