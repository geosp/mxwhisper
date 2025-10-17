"""
LLM service for topic-based semantic chunking.

Uses an OpenAI-compatible LLM endpoint (Ollama, vLLM, etc.) to identify topic boundaries
in transcripts and create semantically coherent chunks. Falls back to sentence-based
chunking if the LLM fails.

Compatible with:
- Ollama (http://ollama.ai)
- vLLM (https://github.com/vllm-project/vllm)
- Any OpenAI-compatible API server
"""

import json
import logging
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import asyncio

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_log, after_log

from app.config import settings
from ..utils.heartbeat import ProgressTracker

logger = logging.getLogger(__name__)


@dataclass
class ChunkMetadata:
    """Metadata for a single chunk (returned from chunking activity)."""
    chunk_index: int
    text: str
    topic_summary: Optional[str]
    keywords: Optional[List[str]]
    confidence: Optional[float]
    start_time: Optional[float]
    end_time: Optional[float]
    start_char_pos: int
    end_char_pos: int


class OllamaChunker:
    """
    Service for topic-based chunking using LLM via OpenAI-compatible API.

    Works with Ollama, vLLM, or any OpenAI-compatible endpoint.
    Configure via OLLAMA_BASE_URL and OLLAMA_MODEL environment variables.
    """

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout
        self.connect_timeout = settings.ollama_connect_timeout
        self.read_timeout = settings.ollama_read_timeout
        self.max_retries = settings.ollama_max_retries

    async def chunk_by_topics(
        self,
        transcript: str,
        segments: List[Dict[str, Any]],
        progress: Optional[ProgressTracker] = None
    ) -> List[ChunkMetadata]:
        """
        Use Ollama to identify topic boundaries and create chunks.

        Args:
            transcript: Full transcript text
            segments: Whisper segments with timestamps
            progress: Optional progress tracker for heartbeats

        Returns:
            List of ChunkMetadata with topic information
        """
        try:
            if progress:
                progress.update(5, "Preparing transcript for topic analysis")

            # Build prompt for Ollama
            prompt = self._build_chunking_prompt(transcript)

            if progress:
                progress.update(5, "Analyzing topics with Ollama")

            # Call Ollama with retries (non-streaming for reliability)
            response = await self._call_ollama_with_retry(prompt, progress)

            if progress:
                progress.update(20, "Parsing topic boundaries")

            # Parse Ollama response and create chunks
            chunks = self._parse_ollama_response(response, transcript, segments)

            if progress:
                progress.update(20, f"Created {len(chunks)} semantic chunks")

            logger.info(f"Successfully created {len(chunks)} chunks using Ollama")
            return chunks

        except Exception as e:
            logger.warning(f"Ollama chunking failed: {e}. Falling back to sentence-based chunking.")
            if progress:
                progress.update(25, "Ollama failed, using sentence-based fallback")

            return self._fallback_sentence_chunking(transcript, segments)

    async def _call_ollama_with_retry(
        self,
        prompt: str,
        progress: Optional[ProgressTracker] = None
    ) -> str:
        """
        Call Ollama API via OpenAI-compatible endpoint with streaming and tenacity-based retry logic.

        Uses the /v1/chat/completions endpoint which is more reliable for structured output
        and doesn't expose separate thinking tokens (reasoning happens silently).
        """
        
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)),
            before=before_log(logger, logging.INFO),
            after=after_log(logger, logging.INFO),
            reraise=True
        )
        async def _call_ollama():
            # Use more granular timeout configuration
            timeout = httpx.Timeout(
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=30.0,
                pool=self.connect_timeout
            )

            # Use OpenAI-compatible API endpoint for better reliability with structured output
            # This endpoint is more stable and doesn't expose separate thinking tokens
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that analyzes transcripts and returns structured JSON output. Return ONLY valid JSON with no markdown formatting, no code blocks, and no additional explanation."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            request_payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": 0.3,
                "top_p": 0.9,
                "max_tokens": 4000,  # Increased for reasoning models (includes thinking + response)
            }

            # Debug logging - log the request details
            logger.info(f"Ollama request URL: {self.base_url}/v1/chat/completions (OpenAI-compatible)")
            logger.info(f"Ollama request model: {self.model}")
            logger.info(f"Ollama request prompt length: {len(prompt)} chars")
            logger.info(f"Ollama request prompt preview: {prompt[:500]}...")
            logger.debug(f"Full Ollama request payload: {json.dumps(request_payload, indent=2)}")

            full_response = ""
            tokens_received = 0
            chunks_received = 0
            reasoning_tokens = 0  # Track reasoning tokens separately

            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json=request_payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        # OpenAI API uses "data: " prefix for SSE (Server-Sent Events)
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]  # Remove "data: " prefix

                        # Check for [DONE] signal
                        if data_str.strip() == "[DONE]":
                            logger.info(f"Ollama streaming completed. Chunks: {chunks_received}, Response length: {len(full_response)} chars")
                            break

                        try:
                            data = json.loads(data_str)
                            chunks_received += 1

                            # Extract content from the delta
                            if "choices" in data and len(data["choices"]) > 0:
                                choice = data["choices"][0]
                                if "delta" in choice:
                                    delta = choice["delta"]

                                    # Check if there's content (not just reasoning)
                                    if "content" in delta and delta["content"]:
                                        content = delta["content"]
                                        full_response += content
                                        tokens_received += 1

                                        # Update progress every 20 tokens
                                        if progress and tokens_received % 20 == 0:
                                            progress.update(
                                                10 + min(tokens_received // 20, 10),  # Progress from 10% to 20%
                                                f"Generating analysis ({tokens_received} tokens)..."
                                            )

                                    # Track reasoning tokens for Ollama reasoning models (not present in vLLM)
                                    # We log but don't accumulate these - they're internal model thoughts
                                    if "reasoning" in delta and delta["reasoning"]:
                                        reasoning_tokens += 1

                                        # Send heartbeats every 50 reasoning tokens to keep activity alive
                                        if progress and reasoning_tokens % 50 == 0:
                                            progress.update(
                                                5,  # Keep progress at 5% during thinking
                                                f"Model reasoning... ({reasoning_tokens} thinking tokens)"
                                            )
                                            logger.info(f"Reasoning in progress: {reasoning_tokens} tokens processed")

                                # Check if done
                                if choice.get("finish_reason") == "stop":
                                    logger.info(f"Ollama generation finished. Reason: stop")
                                    break

                        except json.JSONDecodeError:
                            # Skip malformed lines
                            logger.debug(f"Skipping non-JSON line: {data_str[:100]}")
                            continue

            logger.info(f"Ollama streaming completed. Total chunks: {chunks_received}, reasoning tokens: {reasoning_tokens}, response tokens: {tokens_received}, response length: {len(full_response)} chars")
            if len(full_response) > 0:
                logger.info(f"Ollama response preview: {full_response[:500]}...")
            else:
                logger.warning(f"Ollama returned empty response after {reasoning_tokens} reasoning tokens")

            return full_response

        try:
            if progress:
                progress.update(10, "Starting topic analysis with Ollama")
            result = await _call_ollama()
            if progress:
                progress.update(15, "Topic analysis completed")
            return result
        except Exception as e:
            logger.error(f"Ollama API failed after {self.max_retries} attempts: {e}")
            raise

    def _build_chunking_prompt(self, transcript: str) -> str:
        """Build the prompt for Ollama topic detection."""
        # Estimate token count (rough: 1 token ≈ 4 characters)
        estimated_tokens = len(transcript) // 4

        return f"""Analyze this transcript and identify topic boundaries for semantic chunking.

Transcript ({estimated_tokens} tokens):
{transcript}

Instructions:
1. Identify where major topics change in the content
2. Each chunk should be {settings.chunk_min_tokens}-{settings.chunk_max_tokens} tokens
3. Chunks MUST align with natural topic boundaries (complete thoughts/sections)
4. For each topic segment, provide:
   - start_pos: character position where topic starts (integer)
   - end_pos: character position where topic ends (integer)
   - topic: 1-2 sentence summary of the topic
   - keywords: 3-5 most important keywords (array of strings)
   - confidence: your confidence in this being a topic boundary (0.0-1.0)

IMPORTANT: Return ONLY valid JSON in this exact format (no markdown, no explanation, no code blocks):
{{
  "chunks": [
    {{
      "start_pos": 0,
      "end_pos": 1234,
      "topic": "Introduction to the main theme and context",
      "keywords": ["introduction", "theme", "overview", "context"],
      "confidence": 0.95
    }},
    {{
      "start_pos": 1234,
      "end_pos": 2456,
      "topic": "Deep dive into the first major concept",
      "keywords": ["concept", "explanation", "details", "analysis"],
      "confidence": 0.90
    }}
  ]
}}

Rules:
- Ensure ALL content is covered (first chunk starts at 0, last chunk ends at {len(transcript)})
- No gaps between chunks
- No overlapping chunks (each chunk's start_pos = previous chunk's end_pos)
- Return pure JSON only
"""

    def _parse_ollama_response(
        self,
        response: str,
        transcript: str,
        segments: List[Dict[str, Any]]
    ) -> List[ChunkMetadata]:
        """Parse Ollama JSON response and map to chunks with timestamps."""
        try:
            # Strip thinking tags if present (some models include <think>...</think> in response)
            original_response = response
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
            response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL | re.IGNORECASE)
            response = re.sub(r'```think.*?```', '', response, flags=re.DOTALL | re.IGNORECASE)
            
            if response != original_response:
                logger.info("Stripped thinking tags from Ollama response")
            
            # Extract JSON from response (handle case where Ollama adds surrounding text)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in Ollama response")

            json_str = json_match.group(0)
            data = json.loads(json_str)

            if "chunks" not in data or not isinstance(data["chunks"], list):
                raise ValueError("Invalid JSON structure from Ollama")

            chunks = []
            invalid_chunks = 0
            for idx, chunk_data in enumerate(data["chunks"]):
                # Validate required fields
                if not all(key in chunk_data for key in ["start_pos", "end_pos"]):
                    logger.warning(f"Chunk {idx} missing required fields, skipping")
                    invalid_chunks += 1
                    continue

                start_pos = int(chunk_data["start_pos"])
                end_pos = int(chunk_data["end_pos"])

                # Validate positions
                if start_pos < 0 or end_pos > len(transcript) or start_pos >= end_pos:
                    logger.warning(f"Chunk {idx} has invalid positions, skipping")
                    invalid_chunks += 1
                    continue

                # Map character positions to Whisper segments for timestamps
                start_time, end_time = self._map_to_timestamps(
                    start_pos, end_pos, transcript, segments
                )

                chunks.append(ChunkMetadata(
                    chunk_index=idx,
                    text=transcript[start_pos:end_pos],
                    topic_summary=chunk_data.get("topic"),
                    keywords=chunk_data.get("keywords", []),
                    confidence=chunk_data.get("confidence"),
                    start_char_pos=start_pos,
                    end_char_pos=end_pos,
                    start_time=start_time,
                    end_time=end_time,
                ))

            # If any chunks were invalid, fall back to sentence chunking for reliability
            if invalid_chunks > 0:
                logger.warning(f"Found {invalid_chunks} invalid chunks out of {len(data['chunks'])} total. Falling back to sentence chunking for complete reliability.")
                raise ValueError(f"Some chunks had invalid positions ({invalid_chunks} invalid)")

            if not chunks:
                raise ValueError("No valid chunks extracted from Ollama response")

            logger.info(f"Successfully parsed {len(chunks)} chunks from Ollama")
            return chunks

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse Ollama response: {e}")
            logger.debug(f"Ollama response was: {response[:500]}...")
            raise

    def _map_to_timestamps(
        self,
        start_char: int,
        end_char: int,
        transcript: str,
        segments: List[Dict[str, Any]]
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Map character positions to timestamps using Whisper segments.

        Whisper segments contain text and timestamps. We need to find which
        segments correspond to the character range and extract timestamps.
        """
        if not segments:
            return None, None

        # Build a mapping of character positions to segments
        current_pos = 0
        start_time = None
        end_time = None

        for segment in segments:
            segment_text = segment.get("text", "")
            segment_start = segment.get("start")
            segment_end = segment.get("end")

            segment_end_pos = current_pos + len(segment_text)

            # Check if this segment contains our start position
            if start_time is None and current_pos <= start_char < segment_end_pos:
                start_time = segment_start

            # Check if this segment contains our end position
            if current_pos <= end_char <= segment_end_pos:
                end_time = segment_end
                break

            current_pos = segment_end_pos

        # Fallback: use first and last segment times if mapping failed
        if start_time is None:
            start_time = segments[0].get("start", 0.0)
        if end_time is None:
            end_time = segments[-1].get("end", 0.0)

        return start_time, end_time

    def _fallback_sentence_chunking(
        self,
        transcript: str,
        segments: List[Dict[str, Any]]
    ) -> List[ChunkMetadata]:
        """
        Fallback to simple sentence-based chunking if Ollama fails.

        This creates chunks by splitting on sentence boundaries, aiming for
        chunk_max_tokens size with chunk_overlap_tokens overlap.
        """
        logger.info("Using sentence-based chunking fallback")

        # Simple sentence splitting (improved regex)
        sentences = re.split(r'(?<=[.!?])\s+', transcript)

        chunks = []
        current_chunk = []
        current_length = 0
        chunk_idx = 0
        char_pos = 0

        target_size = settings.chunk_max_tokens * 4  # Rough char estimate
        overlap_size = settings.chunk_overlap_tokens * 4

        for sentence in sentences:
            sentence_length = len(sentence)

            # If adding this sentence exceeds target, create a chunk
            if current_length + sentence_length > target_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                start_pos = char_pos
                end_pos = char_pos + len(chunk_text)

                start_time, end_time = self._map_to_timestamps(
                    start_pos, end_pos, transcript, segments
                )

                chunks.append(ChunkMetadata(
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    topic_summary=None,  # No topic info in fallback
                    keywords=None,
                    confidence=None,
                    start_char_pos=start_pos,
                    end_char_pos=end_pos,
                    start_time=start_time,
                    end_time=end_time,
                ))

                chunk_idx += 1
                char_pos = end_pos + 1  # +1 for space

                # Keep last few sentences for overlap
                overlap_sentences = []
                overlap_length = 0
                for s in reversed(current_chunk):
                    if overlap_length + len(s) <= overlap_size:
                        overlap_sentences.insert(0, s)
                        overlap_length += len(s)
                    else:
                        break

                current_chunk = overlap_sentences
                current_length = overlap_length

            current_chunk.append(sentence)
            current_length += sentence_length

        # Add final chunk if any content remains
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            start_pos = char_pos
            end_pos = char_pos + len(chunk_text)

            start_time, end_time = self._map_to_timestamps(
                start_pos, end_pos, transcript, segments
            )

            chunks.append(ChunkMetadata(
                chunk_index=chunk_idx,
                text=chunk_text,
                topic_summary=None,
                keywords=None,
                confidence=None,
                start_char_pos=start_pos,
                end_char_pos=end_pos,
                start_time=start_time,
                end_time=end_time,
            ))

        logger.info(f"Created {len(chunks)} chunks using sentence-based fallback")
        return chunks
