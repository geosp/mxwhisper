"""
Topic assignment activity for transcription workflow.
"""

import logging
from typing import Dict, Any

from temporalio import activity
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.services.transcription_service import TranscriptionService
from app.workflows.transcribe.services.ollama_service import OllamaChunker

logger = logging.getLogger(__name__)

@activity.defn
async def assign_topics_activity(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assign topics to a transcription based on chunk topic summaries and LLM analysis.
    Args:
        input_data: Dictionary with:
            - transcription_id: int
            - user_id: str
    Returns:
        Dictionary with assignment results
    """
    transcription_id = input_data["transcription_id"]
    user_id = input_data["user_id"]

    engine = create_async_engine(settings.database_url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:

            # 1. Extract chunk topic summaries
            summaries = await TranscriptionService.get_chunk_topic_summaries(session, transcription_id)
            logger.info(f"Extracted {len(summaries)} chunk topic summaries", extra={"transcription_id": transcription_id})

            # 2. Fetch canonical topics (including Unknown)
            from app.services.topic_service import TopicService
            canonical_topics = await TopicService.get_all_topics(session)
            topic_names_list = [t.name for t in canonical_topics]
            topic_names_list_str = '\n'.join(f'- {name}' for name in topic_names_list)

            # 3. Build LLM prompt with canonical topics
            prompt = (
                "Given the following list of topic summaries from audio chunks, "
                "choose the main topics that best describe the overall content. "
                "You MUST select only from the provided list of canonical topics below. "
                "If none fit, use 'Unknown'. Return a comma-separated list of topic names from the list.\n\n"
                "Chunk topic summaries:\n" + '\n'.join(f'- {s}' for s in summaries) +
                "\n\nCanonical topics (choose only from these):\n" + topic_names_list_str
            )

            class LLMClient:
                async def complete(self, prompt):
                    chunker = OllamaChunker()
                    return await chunker._call_ollama_with_retry(prompt)

            llm_client = LLMClient()
            topic_names = await TranscriptionService.analyze_topic_summaries_with_llm(
                summaries,
                llm_client,
                override_prompt=prompt,
                canonical_topic_names=topic_names_list
            )
            logger.info(f"LLM returned topics: {topic_names}", extra={"transcription_id": transcription_id})

            # 3. Map to canonical topic IDs
            topic_ids = await TranscriptionService.map_topics_to_ids(session, topic_names)
            logger.info(f"Mapped to topic IDs: {topic_ids}", extra={"transcription_id": transcription_id})

            # 4. Assign topics
            assignments = await TranscriptionService.assign_topics_to_transcription(
                db=session,
                transcription_id=transcription_id,
                topic_ids=topic_ids,
                user_id=user_id,
                ai_confidence=1.0 if topic_ids else None,
                ai_reasoning="Assigned by LLM based on chunk summaries"
            )
            logger.info(f"Assigned {len(assignments)} topics", extra={"transcription_id": transcription_id})

            await session.commit()

            return {
                "transcription_id": transcription_id,
                "assigned_topic_ids": topic_ids,
                "success": True
            }
    except Exception as e:
        logger.error(f"Topic assignment failed", extra={
            "transcription_id": transcription_id,
            "user_id": user_id,
            "error": str(e)
        }, exc_info=True)
        raise
    finally:
        await engine.dispose()
