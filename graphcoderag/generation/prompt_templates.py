"""
Prompt Templates -- Structured prompts for LLM code Q&A.

Responsibilities:
- Define prompt templates for different query types (Q&A, explain, debug)
- Format retrieved context into a structured prompt
- Build the final prompt by combining system message, context, and query

Usage:
    from graphcoderag.generation.prompt_templates import build_prompt
    prompt = build_prompt(query="How does X work?", context_chunks=results)
"""
from typing import List


# ── System Prompts ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert code assistant analyzing a Python codebase. \
You have been given relevant code context retrieved from the repository's knowledge graph \
and vector embeddings. Answer the developer's question accurately, referencing specific \
file paths, function names, class names, and line numbers from the context.

Rules:
1. Use the provided code context as your primary source. If the context is \
incomplete for a conceptual or API-surface question, you may supplement with \
your own knowledge of the library, but clearly mark which parts of your answer \
come from the context (cite the file/chunk) versus your prior knowledge.
2. Always cite specific files and function/class names when referencing code.
3. Use code snippets from the context to support your explanations.
4. Be concise but thorough. Prioritize accuracy over verbosity.
5. If the question is about a bug or error, trace the code flow step by step."""


# ── Prompt Templates ────────────────────────────────────────────────────

CODE_QA_TEMPLATE = """## Retrieved Code Context

{context}

## Developer's Question

{query}

## Your Answer
"""

CODE_EXPLAIN_TEMPLATE = """## Retrieved Code Context

{context}

## Request

Explain in detail how the following works in this codebase: {query}

Focus on:
1. The main entry point or class involved
2. The control flow and key method calls
3. Any important design patterns or architectural decisions
4. Relevant dependencies and imports

## Your Explanation
"""

CODE_DEBUG_TEMPLATE = """## Retrieved Code Context

{context}

## Bug/Issue Description

{query}

## Your Analysis

Please analyze the code and:
1. Identify the likely root cause
2. Trace the execution flow that leads to the issue
3. Suggest a specific fix with code
"""


# ── Helper Functions ────────────────────────────────────────────────────

def format_context(results: list, max_chunks: int = 10) -> str:
    """
    Format retrieval results into a structured context string for the LLM.

    Args:
        results: List of RetrievalResult objects from the hybrid retriever.
        max_chunks: Maximum number of chunks to include.

    Returns:
        Formatted context string with file paths, names, and source code.
    """
    if not results:
        return "(No relevant code context found.)"

    parts = []
    for i, r in enumerate(results[:max_chunks], 1):
        # Build the header
        name = getattr(r, 'display_name', None) or getattr(r, 'name', 'unknown')
        file_path = getattr(r, 'file_path', 'unknown')
        chunk_type = getattr(r, 'chunk_type', 'code')
        start = getattr(r, 'start_line', 0)
        end = getattr(r, 'end_line', 0)
        source = getattr(r, 'source', 'unknown')
        score = getattr(r, 'score', 0.0)

        header = f"### [{i}] {chunk_type.title()}: `{name}` ({file_path}:{start}-{end})"
        header += f"\n*Source: {source} | Score: {score:.3f}*"

        # Add docstring if available
        docstring = getattr(r, 'docstring', '')
        if docstring:
            header += f"\n*Docstring: {docstring[:200]}*"

        # Add source code
        source_code = getattr(r, 'source_code', '')
        if source_code:
            # Strip the metadata prefix if present (from to_embedding_text)
            code_lines = source_code.split('\n')
            clean_lines = [l for l in code_lines if not l.startswith('# File:')
                          and not l.startswith('# Function:')
                          and not l.startswith('# Class:')
                          and not l.startswith('# Module:')
                          and not l.startswith('# Docstring:')]
            clean_code = '\n'.join(clean_lines).strip()
            if clean_code:
                header += f"\n```python\n{clean_code}\n```"

        parts.append(header)

    return '\n\n'.join(parts)


def build_prompt(
    query: str,
    context_chunks: list,
    template: str = "qa",
    max_context_chunks: int = 10,
) -> str:
    """
    Build a complete prompt by combining template, context, and query.

    Args:
        query: The developer's question.
        context_chunks: List of RetrievalResult objects.
        template: Prompt template type: "qa", "explain", or "debug".
        max_context_chunks: Maximum chunks to include in context.

    Returns:
        Complete formatted prompt string ready for the LLM.
    """
    context = format_context(context_chunks, max_chunks=max_context_chunks)

    templates = {
        "qa": CODE_QA_TEMPLATE,
        "explain": CODE_EXPLAIN_TEMPLATE,
        "debug": CODE_DEBUG_TEMPLATE,
    }

    tmpl = templates.get(template, CODE_QA_TEMPLATE)

    return tmpl.format(
        context=context,
        query=query,
    )


def get_system_message() -> str:
    """Return the system prompt for use with chat-style APIs."""
    return SYSTEM_PROMPT
