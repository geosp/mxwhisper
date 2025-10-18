"""
Test the OllamaChunker service with vLLM backend.

This test verifies that the chunker can communicate with a vLLM server
using the OpenAI-compatible API endpoint.
"""
import asyncio
import logging
import os

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from app.workflows.transcribe.services.ollama_service import OllamaChunker
from app.config import settings

# Sample transcript to test with
sample_transcript = """Hello, welcome to this demonstration. Today we'll be discussing
several important topics related to machine learning and artificial intelligence.
First, let's talk about neural networks and how they work. Neural networks are
computing systems inspired by biological neural networks. They consist of interconnected
nodes or neurons that process information. Next, we'll explore deep learning, which
uses multiple layers to progressively extract higher-level features from raw input."""

# Sample segments (from Whisper)
sample_segments = [
    {
        "start": 0.0,
        "end": 3.5,
        "text": "Hello, welcome to this demonstration."
    },
    {
        "start": 3.5,
        "end": 8.2,
        "text": "Today we'll be discussing several important topics related to machine learning and artificial intelligence."
    },
    {
        "start": 8.2,
        "end": 12.8,
        "text": "First, let's talk about neural networks and how they work."
    },
    {
        "start": 12.8,
        "end": 18.5,
        "text": "Neural networks are computing systems inspired by biological neural networks."
    },
    {
        "start": 18.5,
        "end": 23.2,
        "text": "They consist of interconnected nodes or neurons that process information."
    },
    {
        "start": 23.2,
        "end": 29.0,
        "text": "Next, we'll explore deep learning, which uses multiple layers to progressively extract higher-level features from raw input."
    }
]

async def test_vllm_health():
    """Test if vLLM server is reachable."""
    import httpx

    print("Testing vLLM server health...")
    print(f"URL: {settings.ollama_base_url}")
    print()

    try:
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try to get available models
            response = await client.get(f"{settings.ollama_base_url}/v1/models")

            if response.status_code == 200:
                print("✓ vLLM server is reachable")
                data = response.json()
                if "data" in data:
                    print(f"✓ Available models: {len(data['data'])}")
                    for model in data["data"]:
                        print(f"  - {model.get('id', 'unknown')}")
                print()
                return True
            else:
                print(f"✗ vLLM server returned status {response.status_code}")
                return False

    except Exception as e:
        print(f"✗ Failed to connect to vLLM server: {e}")
        return False

async def test_vllm_chunking():
    """Test the chunking service with vLLM backend."""
    print("Testing OllamaChunker service with vLLM backend...")
    print(f"Transcript length: {len(sample_transcript)} chars")
    print(f"Segments: {len(sample_segments)}")
    print()

    try:
        chunker = OllamaChunker()

        print(f"vLLM base URL: {chunker.base_url}")
        print(f"Model: {chunker.model}")
        print(f"Connect timeout: {chunker.connect_timeout}s")
        print(f"Read timeout: {chunker.read_timeout}s")
        print(f"Max retries: {chunker.max_retries}")
        print()

        print("Calling chunk_by_topics()...")
        print("(This may take a while depending on the model size and server load)")
        print()

        chunks = await chunker.chunk_by_topics(
            transcript=sample_transcript,
            segments=sample_segments,
            progress=None  # No progress tracker for this test
        )

        print()
        print("=" * 80)
        print("SUCCESS!")
        print("=" * 80)
        print(f"Created {len(chunks)} chunks")
        print()

        for i, chunk in enumerate(chunks):
            print(f"Chunk {i}:")
            print(f"  Text: {chunk.text[:100]}...")
            print(f"  Topic: {chunk.topic_summary}")
            print(f"  Keywords: {chunk.keywords}")
            print(f"  Confidence: {chunk.confidence}")
            print(f"  Time: {chunk.start_time}s - {chunk.end_time}s")
            print(f"  Character range: {chunk.start_char_pos}-{chunk.end_char_pos}")
            print()

    except Exception as e:
        print()
        print("=" * 80)
        print("ERROR!")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

async def main():
    """Run all tests."""
    print("=" * 80)
    print("vLLM SERVICE TEST")
    print("=" * 80)
    print()

    # First check if vLLM server is reachable
    health_ok = await test_vllm_health()

    if not health_ok:
        print()
        print("=" * 80)
        print("SKIPPING CHUNKING TEST - vLLM server is not reachable")
        print("=" * 80)
        print()
        print("Please check:")
        print(f"1. Is vLLM server running at {settings.ollama_base_url}?")
        print("2. Is the URL correct in your .env file or app/config.py?")
        print("3. Is there a firewall blocking the connection?")
        return

    print()
    print("-" * 80)
    print()

    # Run chunking test
    success = await test_vllm_chunking()

    print()
    print("=" * 80)
    if success:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
