#!/bin/bash

# MxWhisper API Test Script
# Uploads an audio file and retrieves the transcription

set -e  # Exit on any error

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
AUTH_TOKEN="${AUTH_TOKEN:-}"  # Set this if authentication is required

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    echo "Usage: $0 <audio_file_path> [options]"
    echo ""
    echo "Upload an audio file for transcription and retrieve the result."
    echo ""
    echo "Arguments:"
    echo "  audio_file_path    Path to the audio file to transcribe"
    echo ""
    echo "Options:"
    echo "  -u, --url URL     API base URL (default: $API_BASE_URL)"
    echo "  -t, --token TOKEN Authentication token (if required)"
    echo "  -w, --wait SEC    Wait time between status checks (default: 5)"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 audio.mp3"
    echo "  $0 audio.wav --url http://my-api.com --token abc123"
    echo "  $0 /path/to/audio.m4a --wait 10"
}

# Try to load token from .env file if not set
if [[ -z "$AUTH_TOKEN" && -f "../../.env" ]]; then
    # Look for a TEST_TOKEN or similar in .env
    TEST_TOKEN=$(grep -E "^(TEST_TOKEN|API_TOKEN)=" "../../.env" | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
    if [[ -n "$TEST_TOKEN" ]]; then
        AUTH_TOKEN="$TEST_TOKEN"
        log_info "Using token from .env file"
    else
        log_warning "No token found in .env file. You can:"
        log_warning "  1. Add TEST_TOKEN=your-jwt-token to .env"
        log_warning "  2. Use --token option: $0 file.mp3 --token your-token"
        log_warning "  3. Generate a token: uv run python scripts/create_api_user.py --username test --email test@example.com --role user"
        echo ""
    fi
fi

# Parse arguments
AUDIO_FILE=""
WAIT_TIME=5

while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--url)
            API_BASE_URL="$2"
            shift 2
            ;;
        -t|--token)
            AUTH_TOKEN="$2"
            shift 2
            ;;
        -w|--wait)
            WAIT_TIME="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            if [[ -z "$AUDIO_FILE" ]]; then
                AUDIO_FILE="$1"
            else
                log_error "Multiple audio files specified"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [[ -z "$AUDIO_FILE" ]]; then
    log_error "Audio file path is required"
    show_usage
    exit 1
fi

if [[ ! -f "$AUDIO_FILE" ]]; then
    log_error "Audio file does not exist: $AUDIO_FILE"
    exit 1
fi

# Prepare curl headers
CURL_HEADERS=()
if [[ -n "$AUTH_TOKEN" ]]; then
    CURL_HEADERS+=(-H "Authorization: Bearer $AUTH_TOKEN")
fi

log_info "Starting transcription test"
log_info "API URL: $API_BASE_URL"
log_info "Audio file: $AUDIO_FILE"
log_info "Wait time: ${WAIT_TIME}s"

# Step 1: Upload the file
log_info "Uploading audio file..."

UPLOAD_RESPONSE=$(curl -s -X POST \
    "${CURL_HEADERS[@]}" \
    -F "file=@$AUDIO_FILE" \
    "$API_BASE_URL/upload" 2>/dev/null)

if [[ $? -ne 0 ]]; then
    log_error "Failed to upload file"
    exit 1
fi

# Extract job ID from response
# Assuming the response contains a job ID in JSON format like {"job_id": "job-123", ...}
JOB_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"job_id"[^,]*' | sed 's/.*"job_id":\s*\([0-9]*\).*/\1/' 2>/dev/null || echo "")

if [[ -z "$JOB_ID" ]]; then
    log_error "Failed to extract job ID from upload response"
    log_error "Response: $UPLOAD_RESPONSE"
    exit 1
fi

log_success "File uploaded successfully"
log_info "Job ID: $JOB_ID"

# Step 2: Wait for completion
log_info "Waiting for transcription to complete..."

STATUS="pending"
ATTEMPTS=0
MAX_ATTEMPTS=120  # 10 minutes max (120 * 5s)

while [[ "$STATUS" != "completed" && "$STATUS" != "failed" ]]; do
    ATTEMPTS=$((ATTEMPTS + 1))

    if [[ $ATTEMPTS -gt $MAX_ATTEMPTS ]]; then
        log_error "Transcription timed out after $(($MAX_ATTEMPTS * $WAIT_TIME)) seconds"
        exit 1
    fi

    sleep $WAIT_TIME

    # Check job status
    STATUS_RESPONSE=$(curl -s "${CURL_HEADERS[@]}" "$API_BASE_URL/job/$JOB_ID" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_warning "Failed to check job status (attempt $ATTEMPTS)"
        continue
    fi

    # Extract status from response
    STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status"[^,]*' | sed 's/.*"status":\s*"\([^"]*\)".*/\1/' 2>/dev/null || echo "unknown")

    case "$STATUS" in
        "pending")
            log_info "Job status: Pending... (attempt $ATTEMPTS)"
            ;;
        "processing")
            log_info "Job status: Processing... (attempt $ATTEMPTS)"
            ;;
        "completed")
            log_success "Transcription completed!"
            break
            ;;
        "failed")
            log_error "Transcription failed"
            exit 1
            ;;
        *)
            log_warning "Unknown status: $STATUS (attempt $ATTEMPTS)"
            ;;
    esac
done

# Step 3: Download the transcript
log_info "Downloading transcript..."

TRANSCRIPT_RESPONSE=$(curl -s "${CURL_HEADERS[@]}" "$API_BASE_URL/jobs/$JOB_ID/download?format=srt" 2>/dev/null)

if [[ $? -ne 0 ]]; then
    log_error "Failed to download transcript"
    exit 1
fi

# Check if we got actual transcript content (not an error)
if [[ ${#TRANSCRIPT_RESPONSE} -lt 10 ]]; then
    log_error "Received empty or invalid transcript response"
    log_error "Response: $TRANSCRIPT_RESPONSE"
    exit 1
fi

log_success "Transcript downloaded successfully!"
echo ""
echo "=== TRANSCRIPT ==="
echo "$TRANSCRIPT_RESPONSE"
echo "=================="

# Optional: Save to file
OUTPUT_FILE="${AUDIO_FILE%.*}_transcript.srt"
echo "$TRANSCRIPT_RESPONSE" > "$OUTPUT_FILE"
log_info "Transcript also saved to: $OUTPUT_FILE"

log_success "Transcription test completed successfully!"