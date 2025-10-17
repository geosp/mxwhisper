import asyncio
import json
import httpx
import time

async def test_ollama_streaming():
    print("Testing Ollama streaming directly...")

    url = "http://ollamas.mixwarecs-home.net/api/generate"
    prompt = "Say hello world briefly"

    timeout = httpx.Timeout(connect=60.0, read=300.0, write=30.0, pool=60.0)

    start_time = time.time()
    messages_received = 0
    full_response = ""
    thinking_tokens = 0
    response_tokens = 0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                json={
                    "model": "gpt-oss:20b",
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                    }
                }
            ) as response:
                response.raise_for_status()
                print(f"Response status: {response.status_code}\n")

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    messages_received += 1

                    try:
                        # Ollama streams JSON objects directly (no "data: " prefix)
                        data = json.loads(line)

                        # Track thinking vs response tokens
                        if "thinking" in data and data["thinking"]:
                            thinking_tokens += 1

                        # Only accumulate response tokens
                        if "response" in data and data["response"]:
                            full_response += data["response"]
                            response_tokens += 1
                            print(f"Response token {response_tokens}: '{data['response']}'")

                        # Check if generation is done
                        if data.get("done", False):
                            print("\n=== Generation completed! ===")
                            break

                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        continue

                end_time = time.time()
                total_time = end_time - start_time
                print(f"\nFull response: {full_response}")
                print(f"\nCompleted in {total_time:.1f} seconds")
                print(f"Total messages received: {messages_received}")
                print(f"Thinking tokens: {thinking_tokens}")
                print(f"Response tokens: {response_tokens}")
                
    except Exception as e:
        end_time = time.time()
        total_time = end_time - start_time
        print(f"Error after {total_time:.1f} seconds: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ollama_streaming())
