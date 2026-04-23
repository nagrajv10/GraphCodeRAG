"""
FAISS Vector Store — High-performance similarity search with SFR embeddings.

Advantages over ChromaDB:
- Direct control over index type (IndexFlatIP for cosine, IndexIVFFlat for scale)
- No ORM overhead — raw numpy arrays → FAISS index
- Faster search on large collections (41K+ chunks)
- Persistent: saves index + metadata to disk

Usage:
    from graphcoderag.storage.faiss_store import FaissVectorStore
    store = FaissVectorStore(collection_name="click_sfr")
    store.add_chunks(chunks)
    results = store.search("how does routing work?", top_k=10)
"""
import os
import json
import numpy as np
import faiss
from typing import List, Dict, Any, Optional
from pathlib import Path

from graphcoderag.config import FAISS_INDEX_DIR, SFR_EMBEDDING_DIMENSION
from graphcoderag.storage.embedding import embed_texts, embed_query

import logging
logger = logging.getLogger(__name__)


class FaissVectorStore:
    """FAISS-based vector store with SFR-Embedding-Code-400M_R embeddings."""

    def __init__(self, collection_name: str = "code_chunks"):
        self.collection_name = collection_name
        self.dimension = SFR_EMBEDDING_DIMENSION  # 1024 for SFR
        self.index_dir = Path(FAISS_INDEX_DIR) / collection_name
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.index_dir / "index.faiss"
        self.meta_path = self.index_dir / "metadata.json"

        # In-memory state
        self.index: Optional[faiss.IndexFlatIP] = None
        self.metadata: List[Dict[str, Any]] = []
        self.chunk_ids: List[str] = []

        self._load()

    def _load(self):
        """Load existing index + metadata from disk, or create empty."""
        if self.index_path.exists() and self.meta_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, "r") as f:
                saved = json.load(f)
            self.metadata = saved.get("metadata", [])
            self.chunk_ids = saved.get("chunk_ids", [])
            logger.info(f"FAISS[{self.collection_name}] loaded: {self.index.ntotal} vectors")
        else:
            # IndexFlatIP = inner-product (equivalent to cosine on L2-normalized vectors)
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []
            self.chunk_ids = []

    def _save(self):
        """Persist index + metadata to disk."""
        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "w") as f:
            json.dump({
                "chunk_ids": self.chunk_ids,
                "metadata": self.metadata,
            }, f)

    def add_chunks(self, chunks: list, batch_size: int = 64):
        """
        Embed and store code chunks.

        Args:
            chunks: List of CodeChunk objects with .to_embedding_text(), .chunk_id, etc.
            batch_size: Embedding batch size (for GPU memory management).
        """
        if not chunks:
            return

        # Prepare texts and metadata
        texts = []
        metas = []
        ids = []

        existing_ids = set(self.chunk_ids)

        for c in chunks:
            if c.chunk_id in existing_ids:
                continue  # Skip duplicates
            texts.append(c.to_embedding_text())
            ids.append(c.chunk_id)
            metas.append({
                "file_path": c.file_path,
                "chunk_type": c.chunk_type,
                "name": c.display_name,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "docstring": (c.docstring or "")[:500],
                "parent_class": c.parent_class or "",
            })

        if not texts:
            return

        # Embed in batches
        logger.info(f"Embedding {len(texts)} chunks with SFR model...")
        embeddings = embed_texts(texts, batch_size=batch_size, show_progress=len(texts) > 100)

        # Add to FAISS index
        self.index.add(embeddings)
        self.chunk_ids.extend(ids)
        self.metadata.extend(metas)

        # Persist
        self._save()
        logger.info(f"FAISS[{self.collection_name}]: {self.index.ntotal} total vectors")

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for code chunks most similar to the query.

        Args:
            query: Natural language query string.
            top_k: Number of results to return.

        Returns:
            List of dicts with: chunk_id, document, metadata, distance.
        """
        if self.index.ntotal == 0:
            return []

        k = min(top_k, self.index.ntotal)

        # Embed query
        q_emb = embed_query(query)

        # Search (inner product on normalized vectors = cosine similarity)
        scores, indices = self.index.search(q_emb, k)

        results = []
        for i in range(k):
            idx = int(indices[0][i])
            if idx < 0 or idx >= len(self.chunk_ids):
                continue
            results.append({
                "chunk_id": self.chunk_ids[idx],
                "document": "",  # We don't store raw text in FAISS (saves memory)
                "metadata": self.metadata[idx],
                "distance": 1.0 - float(scores[0][i]),  # Convert similarity to distance
            })
        return results

    def get_embedding_by_id(self, chunk_id: str) -> Optional[np.ndarray]:
        """Retrieve the stored embedding vector for a specific chunk_id."""
        if chunk_id not in self.chunk_ids:
            return None
        idx = self.chunk_ids.index(chunk_id)
        return self.index.reconstruct(idx)

    def clear(self):
        """Delete the index and start fresh."""
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = []
        self.chunk_ids = []
        # Remove files
        if self.index_path.exists():
            os.remove(self.index_path)
        if self.meta_path.exists():
            os.remove(self.meta_path)

    def count(self) -> int:
        """Return the number of vectors in the index."""
        return self.index.ntotal
