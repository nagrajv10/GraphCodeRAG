"""
Shared Embedding Module — CodeSearch DistilRoBERTa

Model: flax-sentence-embeddings/st-codesearch-distilroberta-base
- 768-dimensional embeddings
- 512 max token context (memory-efficient on CPU)
- Trained on CodeSearchNet (NL→code retrieval pairs)
- Proven: AST beats Standard RAG on all 4 SWE-bench repos

Singleton pattern: the model is loaded once and shared across all callers.
"""
import numpy as np
from typing import List
from graphcoderag.config import SFR_EMBEDDING_MODEL, SFR_EMBEDDING_DIMENSION

import logging
logger = logging.getLogger(__name__)

_model = None


def get_embedder():
    """Lazy-load the code embedding model (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {SFR_EMBEDDING_MODEL}")
        _model = SentenceTransformer(SFR_EMBEDDING_MODEL)
        logger.info(f"Model loaded. Dimension: {SFR_EMBEDDING_DIMENSION}")
    return _model


def get_dimension() -> int:
    """Return the embedding dimension."""
    return SFR_EMBEDDING_DIMENSION


def embed_texts(texts: List[str], batch_size: int = 64, show_progress: bool = False) -> np.ndarray:
    """Embed a list of texts.

    Returns:
        np.ndarray of shape (len(texts), 768), float32, L2-normalized.
    """
    model = get_embedder()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,
    )
    return np.array(embeddings, dtype=np.float32)


def embed_query(query: str) -> np.ndarray:
    """Embed a single query string."""
    return embed_texts([query])
