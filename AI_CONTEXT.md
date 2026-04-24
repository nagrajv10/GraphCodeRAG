# GraphCodeRAG: Complete Project Architecture & Context

**Purpose:** This document is the ultimate ground-truth reference for `GraphCodeRAG`. It is written specifically for future AI coding assistants to instantly understand the system's architecture, how it understands code better than a standard RAG system, the challenges overcome during development, and the exact flow of data.

---

## 1. How Our System Understands Code (vs. Standard RAG)

A "Standard RAG" system treats code like a regular book: it chops files into arbitrary 500-token chunks. This is catastrophic for code because it cuts functions in half, loses import context, and destroys the structural relationship between classes and methods.

**How GraphCodeRAG solves this:**
Our system actually *understands* code syntax. During the Ingestion phase (`graphcoderag/ingestion/ast_parser.py`), we use an Abstract Syntax Tree (AST) parser to read the Python code as a compiler would. 
*   We extract exact boundaries of `Functions` and `Classes`.
*   We map exactly which file `IMPORTS` which module.
*   We map exactly which function `CALLS` another function.

This allows us to treat code structurally rather than as raw text.

---

## 2. Parent-Child Node Representation & Efficient Retrieval

Instead of just dumping code into a vector database, we map the structural hierarchy into our **Neo4j Graph Database**:
*   `File` (Parent) `CONTAINS` -> `Class` (Child)
*   `Class` (Parent) `CONTAINS` -> `Function` (Child)

**Why this makes retrieval highly efficient:**
If a user asks about `DatabaseConnection.connect()`, a Standard RAG might retrieve the 10 lines of the `connect()` function, but leave out the class initialization variables (like `self.uri`), making the LLM's answer hallucinate.
In GraphCodeRAG:
1.  The Vector DB finds the `connect()` function node.
2.  The Graph DB instantly traverses *up* the tree to find its Parent `Class` node.
3.  It pulls the parent class definition and any sibling methods it calls.
4.  This gives the LLM the exact, holistic context required to write compiling code.

---

## 3. The Hybrid Search Pipeline (Data Flow)

When a user asks a question (or during the SWE-bench evaluation), the data flows through the `HybridRetriever`:

1.  **Semantic Search (FAISS):** The user's query is embedded using `nomic-ai/CodeRankEmbed` (a highly optimized code-embedding model). FAISS searches the vector space and returns the Top-K most semantically similar code chunks.
2.  **Graph Expansion (Neo4j):** For each chunk retrieved by FAISS, we query Neo4j for its structural neighbors (e.g., "What functions call this function?", "What file is this in?").
3.  **Cross-Encoder Reranking:** We combine the semantic chunks and the graph neighbors into one massive pool. We then pass this pool through a HuggingFace Cross-Encoder (`ms-marco-MiniLM-L-6-v2`). The cross-encoder looks at the user's query and the code chunk simultaneously, scoring them for direct relevance, and returns the absolute best chunks to the LLM.

---

## 4. Why We Chose FAISS over ChromaDB

Initially, the project was designed with ChromaDB. However, as we scaled up to evaluate massive repositories like `django` (300k+ lines of code, 160,000+ chunks), we hit severe bottlenecks:
*   **SQLite Locking:** ChromaDB uses SQLite under the hood. When trying to ingest massive amounts of AST-parsed code chunks concurrently, the database locked up.
*   **Disk I/O Slowdown:** ChromaDB persists to disk continuously, making multi-repository evaluation painfully slow.

**The Solution:** We migrated the primary architecture to **FAISS (Facebook AI Similarity Search)**. 
FAISS is an entirely in-memory, highly optimized vector index. It allowed us to perform nearest-neighbor searches in milliseconds and ingest thousands of chunks instantly without database locks. (ChromaDB is still supported in the codebase via `config.py` for persistence, but FAISS is the default for high-performance evaluation).

---

## 5. Major Challenges Faced & How We Solved Them

### A. The LLM Judge Rate-Limiting & Position Bias
*   **Challenge:** When evaluating generation quality, we used Google Gemini/OpenAI as a "Judge" to score the answers. However, LLMs have a known "Position Bias" (they tend to favor the first answer they read). Furthermore, evaluating 15 questions across 4 pipelines triggered severe `429 Too Many Requests` rate limits.
*   **Solution:** We built a **Position-Swap Debiased Judge** (`llm_judge.py`). The judge evaluates `Answer A vs Answer B`, then flips them to `Answer B vs Answer A`. If the judge disagrees with itself, we score it a tie, ensuring 100% fair metrics. We also implemented exponential backoff loops and successfully transitioned to an OpenAI `gpt-4o-mini` judge for blazing fast, limit-free grading.

### B. Massive Codebase Ingestion Constraints
*   **Challenge:** Generating embeddings for repositories like `django` locally using CPU took over 2+ hours, causing timeouts and memory exhaustion.
*   **Solution:** We swapped the embedding model to `nomic-ai/CodeRankEmbed` (137M parameters), which is significantly smaller but trained specifically on code contrastive pairs, allowing it to punch far above its weight class while running efficiently on local hardware. We also implemented caching, so repositories are only embedded once.

### C. Security Vulnerabilities in the API
*   **Challenge:** To make the project "demo-ready" and safe to expose to a network, the FastAPI backend (`api.py`) had severe vulnerabilities.
*   **Solution:** We conducted a full security audit and implemented:
    *   **SSRF Protection:** Validating URLs before allowing the server to run `git clone` on them (preventing internal network scanning).
    *   **Path Traversal Prevention:** Hardening the `/api/file-content` endpoint to ensure users couldn't read local environment files (e.g., `../../.env`).
    *   **XSS Sanitization:** Using DOMPurify on the frontend to ensure malicious code blocks retrieved by the LLM couldn't execute arbitrary JavaScript in the browser.

---

## 6. How to Run Evaluations

The entire proof of concept is driven by `swebench_runner_v2.py`.
It runs a 4-way comparison:
1.  **Std RAG:** Basic FAISS search.
2.  **AST+Vec:** FAISS search on AST chunks.
3.  **Hybrid:** FAISS + Neo4j + Cross-Encoder.
4.  **Plain LLM:** No context.

To run:
`python -m graphcoderag.evaluation.swebench_runner_v2 --backend=faiss`

*(All API keys and configurations should be managed exclusively via `graphcoderag/config.py` and `.env`)*.
