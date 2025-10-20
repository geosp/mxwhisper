# MxWhisper API Verification Scripts

This directory contains scripts to test and verify the MxWhisper API functionality.

## test_download_transcribe.py

**End-to-end test for the media sourcing architecture**: Download audio from URL → Transcribe

A modern Python script with:
- ✅ Clean JSON parsing using httpx
- ✅ Beautiful console output with rich library
- ✅ Type-safe responses
- ✅ Proper error handling
- ✅ Progress indicators with spinners
- ✅ Reusable as a library

### Usage

```bash
# Basic usage
uv run python test_download_transcribe.py \
    --username gffajardo \
    --video-url https://youtu.be/YpLymgfPzzY

# With all options
uv run python test_download_transcribe.py \
    --username gffajardo \
    --video-url https://youtu.be/YpLymgfPzzY \
    --api-url http://localhost:8000 \
    --model whisper-large-v3 \
    --language en \
    --wait 5
```

### Quick Start

```bash
# 1. Setup authentication (if needed)
uv run python scripts/manage_tokens.py generate gffajardo
echo "TEST_TOKEN=your-token-here" >> .env

# 2. Run the test
cd docker/verify
uv run python test_download_transcribe.py \
    --username gffajardo \
    --video-url https://youtu.be/YpLymgfPzzY
```

### Features

- ✅ **Download from URL**: Tests yt-dlp integration with YouTube, Vimeo, SoundCloud, etc.
- ✅ **Video Metadata**: Extracts video ID, title, platform, duration
- ✅ **Async Workflows**: Tests Temporal workflow integration (DownloadAudioWorkflow + TranscribeWorkflow)
- ✅ **Progress Monitoring**: Real-time status updates with spinners for both download and transcription
- ✅ **New Architecture**: Tests AudioFile + Transcription models
- ✅ **Chunking**: Verifies semantic chunking with topic detection
- ✅ **Error Handling**: Comprehensive error checking at each step

### Requirements

- MxWhisper API running with Temporal worker
- Valid authentication token (required)
- User account exists in database
- Internet connection for downloading videos
- yt-dlp installed in the API environment

### Authentication

**Authentication token is required.** You must provide it via one of these methods:

**Method 1: Environment variable (recommended)**

Add to your `.env` file:
```bash
TEST_TOKEN=your-jwt-token-here
```

**Method 2: Command-line option**

```bash
uv run python test_download_transcribe.py \
    --username gffajardo \
    --video-url https://youtu.be/YpLymgfPzzY \
    --token your-jwt-token-here
```

**To generate a token:**

```bash
# First, ensure user exists
uv run python scripts/manage_users.py create \
    --username gffajardo \
    --email gffajardo@example.com \
    --role user

# Then generate token
uv run python scripts/manage_tokens.py generate gffajardo
```

### Test Steps

The script validates the complete pipeline through 6 steps:

1. **Download Audio from URL** - Creates Job + starts DownloadAudioWorkflow
2. **Monitor Download Progress** - Waits for download to complete with progress spinner
3. **Get Audio File Details** - Shows filename, platform, duration, file size
4. **Create Transcription** - Starts TranscribeWorkflow
5. **Monitor Transcription Progress** - Waits for transcription with progress spinner
6. **Get Transcription Results** - Shows transcript, chunks, confidence

### Example Output

```
┌─────────────────────────────────────────────────────┐
│ MxWhisper End-to-End Test                          │
│ Download from URL → Transcribe                     │
└─────────────────────────────────────────────────────┘

API URL      http://localhost:8000
Username     gffajardo
Video URL    https://youtu.be/YpLymgfPzzY
Whisper Model whisper-large-v3
Wait Time    5s

STEP 1: Download Audio from URL
Initiating download from: https://youtu.be/YpLymgfPzzY
✓ Download job created: Job ID 123

STEP 2: Monitor Download Progress
⠋ Waiting for Download...
✓ Download completed successfully

STEP 3: Get Audio File Details
✓ Audio file ID: 456
Filename     Rick Astley - Never Gonna Give You Up (Official Video).mp3
Platform     youtube
Duration     212.0s
File Size    4.85 MB
Source URL   https://youtu.be/YpLymgfPzzY

STEP 4: Create Transcription
Starting transcription with model: whisper-large-v3
✓ Transcription job created: Job ID 124, Transcription ID 789

STEP 5: Monitor Transcription Progress
⠋ Waiting for transcription...
✓ Transcription completed successfully

STEP 6: Get Transcription Results
Language     en
Confidence   0.89
Chunks       8

╭─ Transcript Preview ─────────────────────────────────╮
│ We're no strangers to love                          │
│ You know the rules and so do I...                   │
╰──────────────────────────────────────────────────────╯

┌─────────────────────────────────────────────────────┐
│ TEST SUMMARY                                        │
│                                                      │
│ ✓ Download from URL successful                     │
│ ✓ Audio file created: Rick Astley... (ID: 456)    │
│ ✓ Platform detected: youtube                       │
│ ✓ Transcription completed (ID: 789)               │
│ ✓ Language detected: en                            │
│ ✓ Chunks created: 8                                │
└─────────────────────────────────────────────────────┘

End-to-end test completed successfully!

You can now:
  • View audio file: GET http://localhost:8000/audio/456
  • View transcription: GET http://localhost:8000/transcriptions/789
  • List all audio files: GET http://localhost:8000/audio
  • List all transcriptions: GET http://localhost:8000/transcriptions
```

### Command-Line Options

```
Required Arguments:
  -u, --username USER    Username for authentication (e.g., gffajardo)
  -v, --video-url URL    Video URL to download (YouTube, Vimeo, etc.)

Options:
  --api-url URL          API base URL (default: http://localhost:8000)
  -t, --token TOKEN      Authentication token (or set TEST_TOKEN in .env)
  -w, --wait SEC         Wait time between status checks (default: 5)
  --model MODEL          Whisper model to use (default: whisper-large-v3)
  --language LANG        Force specific language (e.g., 'en', 'es')
  -h, --help             Show help message
```

### Supported Platforms

The test script works with any platform supported by yt-dlp:
- YouTube (youtube.com, youtu.be)
- Vimeo (vimeo.com)
- SoundCloud (soundcloud.com)
- Twitch (twitch.tv)
- TikTok (tiktok.com)
- And many more...

### Troubleshooting

**"Authentication token is required"**
- Make sure you've added `TEST_TOKEN` to your `.env` file, or use `--token` option
- Generate token: `uv run python scripts/manage_tokens.py generate gffajardo`

**"User not found"**
- Create the user first: `uv run python scripts/manage_users.py create --username gffajardo --email gffajardo@example.com --role user`

**"Download timed out"**
- Increase wait time: `--wait 10`
- Check your internet connection
- Verify yt-dlp is installed and working

**"Transcription failed"**
- Check API logs for errors
- Verify Temporal workers are running
- Ensure Whisper models are available

**"HTTP Error 401"**
- Token is invalid or expired
- Generate a new token: `uv run python scripts/manage_tokens.py generate gffajardo`

**"HTTP Error 404"**
- Audio file or transcription not found
- Job ID may be incorrect
- Check API logs

### Exit Codes

- `0`: Success - All tests passed
- `1`: Error - See output for details

### Using as a Library

The `MxWhisperClient` class can be imported and used in other scripts:

```python
from test_download_transcribe import MxWhisperClient

async def my_test():
    client = MxWhisperClient("http://localhost:8000", "your-token")

    # Download audio
    response = await client.download_audio("https://youtu.be/...")
    job_id = response["job_id"]

    # Check status
    status = await client.get_job_status(job_id)

    await client.close()
```
