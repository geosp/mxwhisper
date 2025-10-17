"""
Embedding service for generating semantic embeddings from text.
Uses sentence-transformers for local, efficient embedding generation.
"""
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Model will be loaded lazily
_model = None


def get_embedding_model() -> SentenceTransformer:
    """
    Lazy load the sentence transformer model.
    Using 'all-MiniLM-L6-v2' which is:
    - Fast (on CPU and GPU)
    - Small model size (~80MB)
    - 384-dimensional embeddings
    - Good performance for semantic search
    """
    global _model
    if _model is None:
        logger.info("Loading embedding model: all-MiniLM-L6-v2")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded successfully")
    return _model


def generate_embedding(text: str) -> list[float]:
    """
    Generate a semantic embedding vector from text.

    Args:
        text: The text to embed

    Returns:
        A 384-dimensional embedding vector as a list of floats
    """
    if not text or not text.strip():
        logger.warning("Attempted to generate embedding for empty text")
        return [0.0] * 384  # Return zero vector for empty text

    model = get_embedding_model()

    # Truncate very long texts to avoid memory issues
    # Most embedding models have a token limit around 512 tokens
    max_chars = 5000  # Roughly ~1000 tokens
    if len(text) > max_chars:
        logger.info(f"Truncating text from {len(text)} to {max_chars} characters for embedding")
        text = text[:max_chars]

    # Generate embedding
    embedding = model.encode(text, convert_to_numpy=True)

    return embedding.tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts efficiently in batch.

    Args:
        texts: List of texts to embed

    Returns:
        List of 384-dimensional embedding vectors
    """
    if not texts:
        return []

    model = get_embedding_model()

    # Truncate long texts
    max_chars = 5000
    truncated_texts = [
        text[:max_chars] if len(text) > max_chars else text
        for text in texts
    ]

    # Generate embeddings in batch (much faster than one-by-one)
    embeddings = model.encode(truncated_texts, convert_to_numpy=True, show_progress_bar=False)

    return [emb.tolist() for emb in embeddings]
