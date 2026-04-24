"""
Vector Store -- ChromaDB interface for storing and searching code embeddings.

Responsibilities:
- Initialize ChromaDB persistent client
- Embed code chunks using OpenAI or local sentence-transformers
- Store embeddings with metadata
- Perform similarity search
- Clear/reset the collection

Usage:
    from graphcoderag.storage.vector_store import VectorStore
    store = VectorStore()
    store.add_chunks(chunks)
    results = store.search("how does authentication work?", top_k=10)
"""
from typing import List, Dict, Any
import chromadb
from graphcoderag.config import (
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME,
    EMBEDDING_MODEL, USE_LOCAL_EMBEDDINGS, OPENAI_API_KEY,
)

import logging
logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB vector store for code chunk embeddings."""

    def __init__(self, collection_name: str = None):
        self.client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self._collection_name = collection_name or CHROMA_COLLECTION_NAME

        # Use Jina code-specialized embeddings via sentence-transformers
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
            from graphcoderag.config import SFR_EMBEDDING_MODEL
            self.embed_fn = SentenceTransformerEmbeddingFunction(
                model_name=SFR_EMBEDDING_MODEL,
                trust_remote_code=True,
            )
        except Exception as e:
            logger.warning(f"Jina model failed ({e}), falling back to MiniLM-L6-v2")
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
            self.embed_fn = SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )

        self.collection = self.client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list, batch_size: int = 50):
        """
        Embed and store code chunks in the vector database.

        Args:
            chunks: List of CodeChunk objects to store.
            batch_size: Number of chunks to upsert per batch (for rate limiting).
        """
        for c in chunks:
            if getattr(c, "is_child", False):
                raise NotImplementedError(
                    "ChromaDB backend does not yet support Two-Tier Child Chunking. "
                    "Please use FAISS backend (VECTOR_BACKEND='faiss') or implement child/parent metadata resolution in ChromaDB."
                )

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            self.collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.to_embedding_text() for c in batch],
                metadatas=[{
                    "file_path": c.file_path,
                    "chunk_type": c.chunk_type,
                    "name": c.display_name,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "docstring": self._truncate_docstring(c.docstring, c.display_name),
                    "parent_class": c.parent_class or "",
                } for c in batch],
            )

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for code chunks most similar to the query.

        Args:
            query: Natural language query string.
            top_k: Number of results to return.

        Returns:
            List of dicts with: chunk_id, document, metadata, distance.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "chunk_id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
        return output

    def clear(self):
        """Delete the collection and recreate it."""
        self.client.delete_collection(self._collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Return the number of chunks in the collection."""
        return self.collection.count()

    @staticmethod
    def _truncate_docstring(docstring: str, chunk_name: str, limit: int = 500) -> str:
        """Truncate docstring for metadata storage, with a warning log."""
        text = docstring or ""
        if len(text) > limit:
            logger.debug(f"Docstring truncated for '{chunk_name}': {len(text)} -> {limit} chars")
            return text[:limit]
        return text
