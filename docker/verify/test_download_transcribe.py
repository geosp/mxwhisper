#!/usr/bin/env python3
"""
MxWhisper End-to-End Test: Download from URL → Transcribe

Tests the complete media sourcing architecture (Phase 1-4):
1. Download audio from URL (YouTube, Vimeo, etc.)
2. Create AudioFile record with metadata
3. Transcribe the audio file
4. Verify complete pipeline works

Usage:
    python test_download_transcribe.py --username gffajardo --video-url https://youtu.be/YpLymgfPzzY

    # With token from CLI
    python test_download_transcribe.py --username gffajardo --video-url https://youtu.be/YpLymgfPzzY --token YOUR_TOKEN

    # With custom options
    python test_download_transcribe.py \
        --username gffajardo \
        --video-url https://youtu.be/YpLymgfPzzY \
        --api-url http://localhost:8000 \
        --model whisper-large-v3 \
        --language en \
        --wait 5
"""

import asyncio
import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv
import os

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env")

console = Console()


@dataclass
class TestConfig:
    """Configuration for the test run"""
    username: str
    video_url: str
    api_url: str = "http://localhost:8000"
    token: Optional[str] = None
    wait_time: int = 5
    model: str = "whisper-large-v3"
    language: Optional[str] = None
    max_download_wait: int = 600  # 10 minutes
    max_transcribe_wait: int = 1200  # 20 minutes


class MxWhisperClient:
    """Client for interacting with MxWhisper API"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    async def download_audio(self, source_url: str) -> Dict[str, Any]:
        """Initiate audio download from URL"""
        response = await self.client.post(
            f"{self.base_url}/audio/download",
            headers=self.headers,
            json={"source_url": source_url}
        )
        response.raise_for_status()
        return response.json()

    async def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get job status"""
        response = await self.client.get(
            f"{self.base_url}/job/{job_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    async def list_audio_files(self, limit: int = 1, offset: int = 0) -> Dict[str, Any]:
        """List audio files"""
        response = await self.client.get(
            f"{self.base_url}/audio",
            headers=self.headers,
            params={"limit": limit, "offset": offset}
        )
        response.raise_for_status()
        return response.json()

    async def get_audio_file(self, audio_file_id: int) -> Dict[str, Any]:
        """Get audio file details"""
        response = await self.client.get(
            f"{self.base_url}/audio/{audio_file_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    async def create_transcription(
        self,
        audio_file_id: int,
        model: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create transcription for audio file"""
        data = {"model": model}
        if language:
            data["language"] = language

        response = await self.client.post(
            f"{self.base_url}/transcriptions/{audio_file_id}/transcribe",
            headers=self.headers,
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def get_transcription(
        self,
        transcription_id: int,
        include_chunks: bool = True
    ) -> Dict[str, Any]:
        """Get transcription details"""
        response = await self.client.get(
            f"{self.base_url}/transcriptions/{transcription_id}",
            headers=self.headers,
            params={"include_chunks": include_chunks}
        )
        response.raise_for_status()
        return response.json()


async def wait_for_job_completion(
    client: MxWhisperClient,
    job_id: int,
    wait_time: int,
    max_wait: int,
    job_type: str = "Job"
) -> str:
    """
    Wait for job to complete with progress indicator

    Returns:
        Final job status (completed or failed)
    """
    elapsed = 0
    attempts = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"[cyan]Waiting for {job_type}...", total=None)

        while elapsed < max_wait:
            attempts += 1
            await asyncio.sleep(wait_time)
            elapsed += wait_time

            try:
                status_response = await client.get_job_status(job_id)
                status = status_response.get("status", "unknown")

                if status == "completed":
                    progress.update(task, description=f"[green]{job_type} completed!")
                    return "completed"
                elif status == "failed":
                    error = status_response.get("error", "Unknown error")
                    progress.update(task, description=f"[red]{job_type} failed: {error}")
                    return "failed"
                elif status == "processing":
                    progress.update(
                        task,
                        description=f"[yellow]{job_type} processing... ({elapsed}s elapsed)"
                    )
                else:
                    progress.update(
                        task,
                        description=f"[cyan]{job_type} {status}... ({elapsed}s elapsed)"
                    )

            except Exception as e:
                console.print(f"[yellow]Warning: Failed to check status (attempt {attempts}): {e}[/yellow]")

        progress.update(task, description=f"[red]{job_type} timed out after {max_wait}s")
        raise TimeoutError(f"{job_type} timed out after {max_wait} seconds")


async def wait_for_transcription_completion(
    client: MxWhisperClient,
    transcription_id: int,
    wait_time: int,
    max_wait: int
) -> str:
    """
    Wait for transcription to complete with progress indicator

    Returns:
        Final transcription status (completed or failed)
    """
    elapsed = 0
    attempts = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Waiting for transcription...", total=None)

        while elapsed < max_wait:
            attempts += 1
            await asyncio.sleep(wait_time)
            elapsed += wait_time

            try:
                transcription = await client.get_transcription(transcription_id, include_chunks=False)
                status = transcription.get("status", "unknown")

                if status == "completed":
                    progress.update(task, description="[green]Transcription completed!")
                    return "completed"
                elif status == "failed":
                    error = transcription.get("error_message", "Unknown error")
                    progress.update(task, description=f"[red]Transcription failed: {error}")
                    return "failed"
                elif status == "processing":
                    progress.update(
                        task,
                        description=f"[yellow]Transcription processing... ({elapsed}s elapsed)"
                    )
                else:
                    progress.update(
                        task,
                        description=f"[cyan]Transcription {status}... ({elapsed}s elapsed)"
                    )

            except Exception as e:
                console.print(f"[yellow]Warning: Failed to check status (attempt {attempts}): {e}[/yellow]")

        progress.update(task, description=f"[red]Transcription timed out after {max_wait}s")
        raise TimeoutError(f"Transcription timed out after {max_wait} seconds")


async def run_test(config: TestConfig) -> bool:
    """
    Run the end-to-end test

    Returns:
        True if test passed, False otherwise
    """
    console.print(Panel.fit(
        "[bold cyan]MxWhisper End-to-End Test[/bold cyan]\n"
        "[white]Download from URL → Transcribe[/white]",
        border_style="cyan"
    ))
    console.print()

    # Display configuration
    config_table = Table(show_header=False, box=None)
    config_table.add_column("Key", style="cyan")
    config_table.add_column("Value", style="white")
    config_table.add_row("API URL", config.api_url)
    config_table.add_row("Username", config.username)
    config_table.add_row("Video URL", config.video_url)
    config_table.add_row("Whisper Model", config.model)
    if config.language:
        config_table.add_row("Language", config.language)
    config_table.add_row("Wait Time", f"{config.wait_time}s")
    console.print(config_table)
    console.print()

    client = MxWhisperClient(config.api_url, config.token)

    try:
        # ================================================================
        # STEP 1: Download Audio from URL
        # ================================================================
        console.print("[bold cyan]STEP 1:[/bold cyan] Download Audio from URL")
        console.print(f"Initiating download from: [white]{config.video_url}[/white]")

        download_response = await client.download_audio(config.video_url)
        download_job_id = download_response["job_id"]

        console.print(f"[green]✓[/green] Download job created: Job ID [bold]{download_job_id}[/bold]")
        console.print()

        # ================================================================
        # STEP 2: Monitor Download Progress
        # ================================================================
        console.print("[bold cyan]STEP 2:[/bold cyan] Monitor Download Progress")

        download_status = await wait_for_job_completion(
            client,
            download_job_id,
            config.wait_time,
            config.max_download_wait,
            "Download"
        )

        if download_status != "completed":
            console.print("[red]✗ Download failed[/red]")
            return False

        console.print("[green]✓[/green] Download completed successfully")
        console.print()

        # ================================================================
        # STEP 3: Get Audio File Details
        # ================================================================
        console.print("[bold cyan]STEP 3:[/bold cyan] Get Audio File Details")

        # List audio files to find the one we just downloaded
        audio_list = await client.list_audio_files(limit=1, offset=0)
        if not audio_list.get("audio_files"):
            console.print("[red]✗ No audio files found[/red]")
            return False

        audio_file_id = audio_list["audio_files"][0]["id"]
        console.print(f"[green]✓[/green] Audio file ID: [bold]{audio_file_id}[/bold]")

        # Get detailed audio file info
        audio_file = await client.get_audio_file(audio_file_id)

        details_table = Table(show_header=False, box=None)
        details_table.add_column("Key", style="cyan")
        details_table.add_column("Value", style="white")
        details_table.add_row("Filename", audio_file.get("original_filename", "N/A"))
        details_table.add_row("Platform", audio_file.get("source_platform", "N/A"))
        details_table.add_row("Duration", f"{audio_file.get('duration', 0):.1f}s")
        details_table.add_row("File Size", f"{audio_file.get('file_size', 0) / 1024 / 1024:.2f} MB")
        details_table.add_row("Source URL", audio_file.get("source_url", "N/A"))
        console.print(details_table)
        console.print()

        # ================================================================
        # STEP 4: Create Transcription
        # ================================================================
        console.print("[bold cyan]STEP 4:[/bold cyan] Create Transcription")
        console.print(f"Starting transcription with model: [white]{config.model}[/white]")

        transcribe_response = await client.create_transcription(
            audio_file_id,
            config.model,
            config.language
        )

        transcribe_job_id = transcribe_response["job_id"]
        transcription_id = transcribe_response["transcription_id"]

        console.print(
            f"[green]✓[/green] Transcription job created: "
            f"Job ID [bold]{transcribe_job_id}[/bold], "
            f"Transcription ID [bold]{transcription_id}[/bold]"
        )
        console.print()

        # ================================================================
        # STEP 5: Monitor Transcription Progress
        # ================================================================
        console.print("[bold cyan]STEP 5:[/bold cyan] Monitor Transcription Progress")

        transcription_status = await wait_for_transcription_completion(
            client,
            transcription_id,
            config.wait_time,
            config.max_transcribe_wait
        )

        if transcription_status != "completed":
            console.print("[red]✗ Transcription failed[/red]")
            return False

        console.print("[green]✓[/green] Transcription completed successfully")
        console.print()

        # ================================================================
        # STEP 6: Get Transcription Results
        # ================================================================
        console.print("[bold cyan]STEP 6:[/bold cyan] Get Transcription Results")

        transcription = await client.get_transcription(transcription_id, include_chunks=True)

        # Display transcription details
        results_table = Table(show_header=False, box=None)
        results_table.add_column("Key", style="cyan")
        results_table.add_column("Value", style="white")
        results_table.add_row("Language", transcription.get("language", "N/A"))
        results_table.add_row("Confidence", f"{transcription.get('avg_confidence', 0):.2f}")
        results_table.add_row("Chunks", str(len(transcription.get("chunks", []))))
        console.print(results_table)
        console.print()

        # Show transcript preview
        transcript = transcription.get("transcript", "")
        preview_length = 500
        transcript_preview = transcript[:preview_length]
        if len(transcript) > preview_length:
            transcript_preview += "..."

        console.print(Panel(
            transcript_preview,
            title="[cyan]Transcript Preview[/cyan]",
            border_style="cyan"
        ))
        console.print()

        # ================================================================
        # Final Summary
        # ================================================================
        console.print(Panel.fit(
            "[bold green]TEST SUMMARY[/bold green]\n\n"
            f"[green]✓[/green] Download from URL successful\n"
            f"[green]✓[/green] Audio file created: {audio_file.get('original_filename', 'N/A')} (ID: {audio_file_id})\n"
            f"[green]✓[/green] Platform detected: {audio_file.get('source_platform', 'N/A')}\n"
            f"[green]✓[/green] Transcription completed (ID: {transcription_id})\n"
            f"[green]✓[/green] Language detected: {transcription.get('language', 'N/A')}\n"
            f"[green]✓[/green] Chunks created: {len(transcription.get('chunks', []))}",
            border_style="green"
        ))
        console.print()

        console.print("[bold green]End-to-end test completed successfully![/bold green]")
        console.print()

        # Show useful URLs
        console.print("[cyan]You can now:[/cyan]")
        console.print(f"  • View audio file: GET {config.api_url}/audio/{audio_file_id}")
        console.print(f"  • View transcription: GET {config.api_url}/transcriptions/{transcription_id}")
        console.print(f"  • List all audio files: GET {config.api_url}/audio")
        console.print(f"  • List all transcriptions: GET {config.api_url}/transcriptions")
        console.print()

        return True

    except httpx.HTTPStatusError as e:
        console.print(f"[red]✗ HTTP Error: {e.response.status_code}[/red]")
        console.print(f"[red]Response: {e.response.text}[/red]")
        return False
    except TimeoutError as e:
        console.print(f"[red]✗ Timeout: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.close()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="MxWhisper End-to-End Test: Download from URL → Transcribe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "-u", "--username",
        required=True,
        help="Username for authentication (e.g., gffajardo)"
    )
    parser.add_argument(
        "-v", "--video-url",
        required=True,
        help="Video URL to download (YouTube, Vimeo, etc.)"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "-t", "--token",
        help="Authentication token (or set TEST_TOKEN in .env)"
    )
    parser.add_argument(
        "-w", "--wait",
        type=int,
        default=5,
        help="Wait time between status checks in seconds (default: 5)"
    )
    parser.add_argument(
        "--model",
        default="whisper-large-v3",
        help="Whisper model to use (default: whisper-large-v3)"
    )
    parser.add_argument(
        "--language",
        help="Force specific language (e.g., 'en', 'es')"
    )

    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_arguments()

    # Get token from args or environment
    token = args.token or os.getenv("TEST_TOKEN")

    if not token:
        console.print("[red]Error: Authentication token is required[/red]")
        console.print()
        console.print("[cyan]Please provide a token using one of these methods:[/cyan]")
        console.print("  1. Add TEST_TOKEN=your-jwt-token to .env")
        console.print(f"  2. Use --token option: {sys.argv[0]} --username {args.username} --video-url {args.video_url} --token your-token")
        console.print()
        console.print(f"[cyan]To generate a token for user '{args.username}':[/cyan]")
        console.print(f"  uv run python scripts/manage_tokens.py generate {args.username}")
        sys.exit(1)

    config = TestConfig(
        username=args.username,
        video_url=args.video_url,
        api_url=args.api_url,
        token=token,
        wait_time=args.wait,
        model=args.model,
        language=args.language
    )

    success = await run_test(config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
