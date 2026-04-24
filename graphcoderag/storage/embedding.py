"""
Shared Embedding Module — CodeRankEmbed

Model: nomic-ai/CodeRankEmbed
- 768-dimensional embeddings
- 8192 max token context (long code support)
- SOTA on CodeSearchNet and CoIR benchmarks
- 137M parameters — runs on GPU (RTX 4050) or CPU
- Trained with contrastive learning on CoRNStack (21M pairs)

Queries MUST use the prefix: "Represent this query for searching relevant code: "
Code snippets are embedded without a prefix.

Singleton pattern: the model is loaded once and shared across all callers.
"""
import numpy as np
from typing import List
from graphcoderag.config import SFR_EMBEDDING_MODEL, SFR_EMBEDDING_DIMENSION

import logging
logger = logging.getLogger(__name__)

_model = None

QUERY_PREFIX = "Represent this query for searching relevant code: "


def get_embedder():
    """Lazy-load the CodeRankEmbed model (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {SFR_EMBEDDING_MODEL}")
        _model = SentenceTransformer(SFR_EMBEDDING_MODEL, trust_remote_code=True)
        logger.info(f"Model loaded. Dimension: {SFR_EMBEDDING_DIMENSION}")
    return _model


def get_dimension() -> int:
    """Return the embedding dimension."""
    return SFR_EMBEDDING_DIMENSION


def embed_texts(texts: List[str], batch_size: int = 8, show_progress: bool = False) -> np.ndarray:
    """Embed a list of code texts (no query prefix).

    Returns:
        np.ndarray of shape (len(texts), 768), float32, L2-normalized.
    """
    model = get_embedder()
    # Truncate long texts to prevent OOM on CPU (8K context × batch → huge attention matrix)
    max_chars = 2048  # ~512 tokens — safe for 16GB RAM
    truncated = [t[:max_chars] if len(t) > max_chars else t for t in texts]
    embeddings = model.encode(
        truncated,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,
    )
    return np.array(embeddings, dtype=np.float32)


def embed_query(query: str) -> np.ndarray:
    """Embed a single query string with the required task prefix."""
    prefixed = QUERY_PREFIX + query
    return embed_texts([prefixed])
