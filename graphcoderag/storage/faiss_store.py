"""
FAISS Vector Store — High-performance similarity search with embeddings.

Advantages over ChromaDB:
- Direct control over index type (IndexFlatIP for cosine, IndexIVFFlat for scale)
- No ORM overhead — raw numpy arrays → FAISS index
- Faster search on large collections (41K+ chunks)
- Persistent: saves index + metadata to disk

Usage:
    from graphcoderag.storage.faiss_store import FaissVectorStore
    store = FaissVectorStore(collection_name="click_embeddings")
    store.add_chunks(chunks)
    results = store.search("how does routing work?", top_k=10)
"""
import os
import json
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from collections import defaultdict

from graphcoderag.config import FAISS_INDEX_DIR, SFR_EMBEDDING_DIMENSION
from graphcoderag.storage.embedding import embed_texts, embed_query

import logging
logger = logging.getLogger(__name__)


class FaissVectorStore:
    """FAISS-based vector store for CodeRankEmbed embeddings."""

    def __init__(self, collection_name: str = "code_chunks"):
        self.collection_name = collection_name
        self.dimension = SFR_EMBEDDING_DIMENSION
        self.index_dir = Path(FAISS_INDEX_DIR) / collection_name
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.index_dir / "index.faiss"
        self.meta_path = self.index_dir / "metadata.json"

        # In-memory state
        self.index: Optional[faiss.IndexFlatIP] = None
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.chunk_ids: List[str] = []

        self._load()

    def _load(self):
        """Load existing index + metadata from disk, or create empty."""
        if self.index_path.exists() and self.meta_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, "r") as f:
                saved = json.load(f)
            self.metadata = saved.get("metadata", {})
            # Handle legacy list format if necessary
            if isinstance(self.metadata, list):
                logger.warning("Converting legacy metadata list to dict")
                old_ids = saved.get("chunk_ids", [])
                self.metadata = {cid: meta for cid, meta in zip(old_ids, self.metadata)}
            self.chunk_ids = saved.get("chunk_ids", [])
            logger.info(f"FAISS[{self.collection_name}] loaded: {self.index.ntotal} vectors")
        else:
            # IndexFlatIP = inner-product (equivalent to cosine on L2-normalized vectors)
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = {}
            self.chunk_ids = []
            
        # Rebuild O(1) lookup cache
        self._rebuild_cache()

    def _rebuild_cache(self):
        """Maintain an O(1) mapping of chunk_id to faiss index."""
        self.id_to_idx = {cid: i for i, cid in enumerate(self.chunk_ids)}
        self._rebuild_metadata_indexes()

    # ── Metadata Reverse Indexes ──────────────────────────────────────

    def _rebuild_metadata_indexes(self):
        """Build in-memory inverted indexes over metadata fields.

        These allow the retrieval layer to ask "give me all chunk_ids
        where parent_class == 'Command'" in O(1) instead of scanning
        the entire metadata dictionary.
        """
        self.file_index: Dict[str, Set[str]] = defaultdict(set)
        self.class_index: Dict[str, Set[str]] = defaultdict(set)
        self.type_index: Dict[str, Set[str]] = defaultdict(set)

        for cid, meta in self.metadata.items():
            fp = meta.get("file_path", "")
            if fp:
                self.file_index[fp].add(cid)
            pc = meta.get("parent_class", "")
            if pc:
                self.class_index[pc].add(cid)
            ct = meta.get("chunk_type", "")
            if ct:
                self.type_index[ct].add(cid)

    def get_ids_by_filter(
        self,
        file_path: Optional[str] = None,
        parent_class: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> Set[str]:
        """Return chunk_ids matching ALL supplied filters (intersection).

        If no filters are provided, returns all chunk_ids.
        """
        sets: List[Set[str]] = []
        if file_path is not None:
            sets.append(self.file_index.get(file_path, set()))
        if parent_class is not None:
            sets.append(self.class_index.get(parent_class, set()))
        if chunk_type is not None:
            sets.append(self.type_index.get(chunk_type, set()))

        if not sets:
            return set(self.chunk_ids)
        result = sets[0]
        for s in sets[1:]:
            result = result & s
        return result

    def get_known_classes(self) -> Set[str]:
        """Return all unique parent_class values in the index."""
        return set(self.class_index.keys())

    def get_known_files(self) -> Set[str]:
        """Return all unique file_path values in the index."""
        return set(self.file_index.keys())

    def get_known_functions(self) -> Set[str]:
        """Return all unique function/method names in the index."""
        funcs: Set[str] = set()
        func_ids = self.type_index.get("function", set())
        for cid in func_ids:
            meta = self.metadata.get(cid)
            if meta:
                name = meta.get("name", "")
                if name:
                    funcs.add(name)
        return funcs

    def search_filtered(
        self,
        query: str,
        top_k: int,
        candidate_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Search only within *candidate_ids* by manual dot-product.

        This avoids building a separate FAISS index per filter
        combination — we just reconstruct the relevant vectors and
        compute inner products with numpy.
        """
        if not candidate_ids:
            return []

        # Fallback: if the filter covers >70% of the index, native FAISS
        # search is faster than reconstructing vectors for manual dot-product.
        if self.index.ntotal > 0 and len(candidate_ids) > 0.7 * self.index.ntotal:
            logger.debug(
                f"search_filtered fallback: candidate set ({len(candidate_ids)}) "
                f"covers >{70}% of index ({self.index.ntotal}), using unfiltered search"
            )
            return self.search(query, top_k)

        from graphcoderag.storage.embedding import embed_query as _embed_query

        q_emb = _embed_query(query)  # shape (1, dim)
        q_vec = q_emb[0]             # shape (dim,)

        scored: List[tuple] = []  # (score, chunk_id)
        for cid in candidate_ids:
            idx = self.id_to_idx.get(cid)
            if idx is None:
                continue
            vec = self.index.reconstruct(idx)  # (dim,)
            score = float(np.dot(q_vec, vec))
            scored.append((score, cid))

        scored.sort(key=lambda t: t[0], reverse=True)
        results = []
        for score, cid in scored[:top_k]:
            results.append({
                "chunk_id": cid,
                "document": "",
                "metadata": self.metadata.get(cid, {}),
                "distance": 1.0 - score,
            })
        return results

    def _save(self):
        """Persist index + metadata to disk atomically."""
        tmp_index = str(self.index_path) + ".tmp"
        tmp_meta = str(self.meta_path) + ".tmp"
        
        faiss.write_index(self.index, tmp_index)
        with open(tmp_meta, "w") as f:
            json.dump({
                "chunk_ids": self.chunk_ids,
                "metadata": self.metadata,
            }, f)
            
        # Atomic replace prevents corruption if process dies
        os.replace(tmp_index, str(self.index_path))
        os.replace(tmp_meta, str(self.meta_path))

    def add_chunks(self, chunks: list, batch_size: int = 8):
        """
        Embed and store code chunks.

        Args:
            chunks: List of CodeChunk objects with .to_embedding_text(), .chunk_id, etc.
            batch_size: Embedding batch size (for GPU memory management).
        """
        if not chunks:
            return

        indexable_texts = []
        indexable_ids = []
        existing_ids = set(self.chunk_ids)

        for c in chunks:
            # Add ALL chunks to metadata (both parent and child)
            if c.chunk_id not in self.metadata:
                self.metadata[c.chunk_id] = {
                    "chunk_id": c.chunk_id,
                    "file_path": c.file_path,
                    "chunk_type": c.chunk_type,
                    "name": c.display_name,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "docstring": (c.docstring or "")[:500],
                    "parent_class": c.parent_class or "",
                    "parent_id": getattr(c, "parent_id", None),
                    "is_child": getattr(c, "is_child", False),
                    "source_code": c.source_code, # Keep source to resolve parent later
                    # ── Richer metadata for retrieval filtering ──
                    "signature": getattr(c, "signature", "") or "",
                    "decorators": getattr(c, "decorators", []),
                    "import_names": getattr(c, "import_names", []),
                }

            # Only index child chunks OR small parent chunks
            if getattr(c, "is_child", False) or len(c.source_code) <= 1500:
                if c.chunk_id not in existing_ids:
                    indexable_texts.append(c.to_embedding_text())
                    indexable_ids.append(c.chunk_id)

        if indexable_texts:
            logger.info(f"Embedding {len(indexable_texts)} chunks...")
            embeddings = embed_texts(indexable_texts, batch_size=batch_size, show_progress=len(indexable_texts) > 100)
            self.index.add(embeddings)
            self.chunk_ids.extend(indexable_ids)
            self._rebuild_cache()

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
            cid = self.chunk_ids[idx]
            results.append({
                "chunk_id": cid,
                "document": "",  # We don't store raw text in FAISS index (saves memory)
                "metadata": self.metadata.get(cid, {}), # Dict lookup by chunk_id
                "distance": 1.0 - float(scores[0][i]),  # Convert similarity to distance
            })
        return results

    def get_chunk_metadata(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Fetch metadata (including source_code) for a specific chunk by ID."""
        return self.metadata.get(chunk_id)

    def get_embedding_by_id(self, chunk_id: str) -> Optional[np.ndarray]:
        """Retrieve the stored embedding vector for a specific chunk_id."""
        idx = self.id_to_idx.get(chunk_id)
        if idx is None:
            return None
        return self.index.reconstruct(idx)

    def clear(self):
        """Delete the index and start fresh."""
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = {}
        self.chunk_ids = []
        self._rebuild_cache()
        # Remove files
        if self.index_path.exists():
            os.remove(self.index_path)
        if self.meta_path.exists():
            os.remove(self.meta_path)

    def count(self) -> int:
        """Return the number of vectors in the index."""
        return self.index.ntotal
