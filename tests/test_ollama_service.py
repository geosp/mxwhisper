"""
Test the actual OllamaChunker service to see if it works end-to-end.
"""
import asyncio
import logging

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from app.workflows.transcribe.services.ollama_service import OllamaChunker

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

async def test_ollama_service():
    print("Testing OllamaChunker service...")
    print(f"Transcript length: {len(sample_transcript)} chars")
    print(f"Segments: {len(sample_segments)}")
    print()

    try:
        chunker = OllamaChunker()

        print(f"Ollama base URL: {chunker.base_url}")
        print(f"Ollama model: {chunker.model}")
        print(f"Connect timeout: {chunker.connect_timeout}s")
        print(f"Read timeout: {chunker.read_timeout}s")
        print()

        print("Calling chunk_by_topics()...")
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
            print()

    except Exception as e:
        print()
        print("=" * 80)
        print("ERROR!")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ollama_service())
