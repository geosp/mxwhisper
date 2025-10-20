"""
DownloadService - Handles URL downloads using yt-dlp for audio extraction
"""
import os
import asyncio
import queue
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from app.config import settings


class DownloadService:
    """Service for downloading audio from URLs using yt-dlp"""

    # yt-dlp configuration for audio extraction
    YT_DLP_OPTS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': 0,  # Best quality
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'writethumbnail': False,
        'writesubtitles': False,
        'writeinfojson': False,  # No metadata files
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    @staticmethod
    def detect_platform(url: str) -> Optional[str]:
        """
        Detect platform from URL.

        Args:
            url: Source URL

        Returns:
            Platform name (youtube, soundcloud, vimeo, etc.) or None
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix
        domain = domain.replace('www.', '')

        # Platform detection
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        elif 'soundcloud.com' in domain:
            return 'soundcloud'
        elif 'vimeo.com' in domain:
            return 'vimeo'
        elif 'spotify.com' in domain:
            return 'spotify'
        elif 'bandcamp.com' in domain:
            return 'bandcamp'
        elif 'mixcloud.com' in domain:
            return 'mixcloud'
        elif 'twitch.tv' in domain:
            return 'twitch'
        elif 'tiktok.com' in domain:
            return 'tiktok'
        elif 'facebook.com' in domain or 'fb.com' in domain:
            return 'facebook'
        elif 'twitter.com' in domain or 'x.com' in domain:
            return 'twitter'
        elif 'reddit.com' in domain:
            return 'reddit'
        elif 'instagram.com' in domain:
            return 'instagram'
        else:
            return 'other'

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.

        Args:
            url: URL to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    async def download_audio(
        source_url: str,
        output_dir: str,
        user_id: str,
        progress_queue: Optional[queue.Queue] = None
    ) -> Dict[str, Any]:
        """
        Download audio from URL using yt-dlp.

        Args:
            source_url: URL to download from
            output_dir: Directory to save the file
            user_id: User ID (for unique temp filename)
            progress_queue: Optional queue to put progress updates into

        Returns:
            Dictionary with:
                - file_path: Path to downloaded file
                - original_filename: Title-based filename
                - platform: Detected platform
                - duration: Duration in seconds (if available)

        Raises:
            ValueError: If URL is invalid or download fails
        """
        if not DownloadService.validate_url(source_url):
            raise ValueError(f"Invalid URL: {source_url}")

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Detect platform
        platform = DownloadService.detect_platform(source_url)

        # Create unique output template
        output_template = os.path.join(output_dir, f"download_{user_id}_%(id)s.%(ext)s")

        # Configure yt-dlp options
        ydl_opts = DownloadService.YT_DLP_OPTS.copy()
        ydl_opts['outtmpl'] = output_template

        # Add progress hook if queue provided
        if progress_queue is not None:
            def progress_hook(d):
                """yt-dlp progress hook that puts updates in the queue"""
                if progress_queue is not None:
                    progress_queue.put(d)

            ydl_opts['progress_hooks'] = [progress_hook]

        try:
            # Import yt-dlp (yt_dlp package)
            import yt_dlp

            # Run yt-dlp in thread pool to avoid blocking
            loop = asyncio.get_event_loop()

            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source_url, download=True)
                    return info

            # Execute download in thread pool
            info = await loop.run_in_executor(None, _download)

            if not info:
                raise ValueError("Failed to extract video information")

            # Get the actual downloaded file path
            # After post-processing, the file will have .mp3 extension
            video_id = info.get('id', 'unknown')
            file_path = os.path.join(output_dir, f"download_{user_id}_{video_id}.mp3")

            # Check if file exists
            if not os.path.exists(file_path):
                # Try to find the file with any extension
                import glob
                pattern = os.path.join(output_dir, f"download_{user_id}_{video_id}.*")
                matches = glob.glob(pattern)
                if matches:
                    file_path = matches[0]
                else:
                    raise ValueError("Downloaded file not found")

            # Extract metadata
            title = info.get('title', 'downloaded_audio')
            duration = info.get('duration')  # in seconds
            original_filename = f"{title}.mp3"

            # Sanitize filename
            from app.services.audio_file_service import AudioFileService
            original_filename = AudioFileService.sanitize_filename(original_filename)

            return {
                'file_path': file_path,
                'original_filename': original_filename,
                'platform': platform,
                'duration': duration,
                'title': title,
                'video_id': video_id
            }

        except Exception as e:
            raise ValueError(f"Failed to download from {source_url}: {str(e)}")

    @staticmethod
    async def is_yt_dlp_available() -> bool:
        """
        Check if yt-dlp is available.

        Returns:
            True if yt-dlp is installed and accessible
        """
        try:
            import yt_dlp
            return True
        except ImportError:
            return False

    @staticmethod
    async def get_video_info(source_url: str) -> Dict[str, Any]:
        """
        Get video information without downloading.

        Args:
            source_url: URL to extract info from

        Returns:
            Dictionary with video metadata

        Raises:
            ValueError: If URL is invalid or info extraction fails
        """
        if not DownloadService.validate_url(source_url):
            raise ValueError(f"Invalid URL: {source_url}")

        try:
            import yt_dlp

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }

            loop = asyncio.get_event_loop()

            def _extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(source_url, download=False)

            info = await loop.run_in_executor(None, _extract_info)

            if not info:
                raise ValueError("Failed to extract video information")

            return {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'platform': DownloadService.detect_platform(source_url),
                'uploader': info.get('uploader'),
                'upload_date': info.get('upload_date'),
                'description': info.get('description'),
                'thumbnail': info.get('thumbnail'),
            }

        except Exception as e:
            raise ValueError(f"Failed to extract info from {source_url}: {str(e)}")
