# MxWhisper API Verification Scripts

This directory contains scripts to test and verify the MxWhisper API functionality.

## test-transcription.sh

A comprehensive script that uploads an audio file for transcription and retrieves the result.

### Usage

```bash
# Basic usage with default settings
./test-transcription.sh audio.mp3

# With custom API URL
./test-transcription.sh audio.wav --url http://localhost:8000

# With authentication token
./test-transcription.sh audio.m4a --token your-jwt-token

# With custom wait time between status checks
./test-transcription.sh audio.mp3 --wait 10

# Full example
./test-transcription.sh /path/to/audio.mp3 \
    --url http://your-api.com \
    --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... \
    --wait 5
```

### Features

- ✅ **File Upload**: Automatically uploads audio files to the API
- ✅ **Progress Monitoring**: Shows job status updates in real-time
- ✅ **Error Handling**: Comprehensive error checking and reporting
- ✅ **Authentication**: Supports JWT token authentication
- ✅ **Flexible Configuration**: Customizable API URL and polling intervals
- ✅ **Result Saving**: Saves transcript to a text file automatically
- ✅ **Timeout Protection**: Prevents infinite waiting with configurable timeouts

### Requirements

- `curl` command-line tool
- Access to MxWhisper API (running locally or remote)
- Valid audio file (mp3, wav, m4a, etc.)

### Output

The script will:
1. Upload your audio file
2. Display job status updates
3. Wait for transcription completion
4. Display the full transcript
5. Save transcript to `{filename}_transcript.txt`

### Environment Variables

You can set default values using environment variables:

```bash
export API_BASE_URL="http://your-api.com"
export AUTH_TOKEN="your-jwt-token"

./test-transcription.sh audio.mp3
```

### Exit Codes

- `0`: Success
- `1`: Error (upload failed, transcription failed, etc.)

### Troubleshooting

- **Connection refused**: Make sure the API server is running
- **Authentication error**: Check your JWT token
- **File not found**: Verify the audio file path
- **Timeout**: Increase wait time with `--wait` option

### Quick Test Example

If you have the MxWhisper API running locally, try this:

```bash
# Test with the included sample file
./test-transcription.sh ../../../tests/data/who_is_jesus.mp3

# Or test with authentication (if required)
./test-transcription.sh ../../../tests/data/who_is_jesus.mp3 --token YOUR_TOKEN
```

This will upload the sample audio file, wait for transcription, and display the results.