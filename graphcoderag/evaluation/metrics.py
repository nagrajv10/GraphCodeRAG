"""
Evaluation Metrics -- IR and RAG quality metrics for comparing retrieval systems.

Metrics implemented:
- MRR (Mean Reciprocal Rank): How high is the first relevant result?
- Recall@K: What fraction of relevant items appear in the top-K results?
- Precision@K: What fraction of top-K results are relevant?
- Hit Rate@K: Did at least one relevant item appear in the top-K?
- NDCG@K: Normalized Discounted Cumulative Gain

Usage:
    from graphcoderag.evaluation.metrics import compute_mrr, compute_recall_at_k
    mrr = compute_mrr(retrieved_ids, relevant_ids)
    recall = compute_recall_at_k(retrieved_ids, relevant_ids, k=10)
"""
import math
from typing import List, Set, Union


def compute_mrr(
    retrieved_ids: List[str],
    relevant_ids: Union[List[str], Set[str]],
) -> float:
    """
    Mean Reciprocal Rank: 1/rank of the first relevant result.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground-truth relevant chunk IDs.

    Returns:
        MRR score (0 to 1). 1.0 = first result is relevant, 0.0 = no relevant result found.
    """
    relevant_set = set(relevant_ids)
    for i, rid in enumerate(retrieved_ids, 1):
        if rid in relevant_set:
            return 1.0 / i
    return 0.0


def compute_recall_at_k(
    retrieved_ids: List[str],
    relevant_ids: Union[List[str], Set[str]],
    k: int = 10,
) -> float:
    """
    Recall@K: Fraction of relevant items found in the top-K results.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground-truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        Recall score (0 to 1).
    """
    relevant_set = set(relevant_ids)
    if not relevant_set:
        return 0.0
    top_k = set(retrieved_ids[:k])
    found = len(top_k & relevant_set)
    return found / len(relevant_set)


def compute_precision_at_k(
    retrieved_ids: List[str],
    relevant_ids: Union[List[str], Set[str]],
    k: int = 10,
) -> float:
    """
    Precision@K: Fraction of top-K results that are relevant.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground-truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        Precision score (0 to 1).
    """
    relevant_set = set(relevant_ids)
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    relevant_in_top_k = sum(1 for rid in top_k if rid in relevant_set)
    return relevant_in_top_k / len(top_k)


def compute_hit_rate_at_k(
    retrieved_ids: List[str],
    relevant_ids: Union[List[str], Set[str]],
    k: int = 10,
) -> float:
    """
    Hit Rate@K: 1 if at least one relevant item is in the top-K, else 0.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground-truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        1.0 or 0.0.
    """
    relevant_set = set(relevant_ids)
    top_k = set(retrieved_ids[:k])
    return 1.0 if top_k & relevant_set else 0.0


def compute_ndcg_at_k(
    retrieved_ids: List[str],
    relevant_ids: Union[List[str], Set[str]],
    k: int = 10,
) -> float:
    """
    NDCG@K: Normalized Discounted Cumulative Gain.

    Measures ranking quality — relevant items higher in the list score better.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground-truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        NDCG score (0 to 1).
    """
    relevant_set = set(relevant_ids)
    top_k = retrieved_ids[:k]

    # DCG: sum of 1/log2(rank+1) for each relevant result
    dcg = 0.0
    for i, rid in enumerate(top_k, 1):
        if rid in relevant_set:
            dcg += 1.0 / math.log2(i + 1)

    # Ideal DCG: all relevant items at the top
    ideal_k = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_k + 1))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def compute_file_recall_at_k(
    retrieved_files: List[str],
    relevant_files: Union[List[str], Set[str]],
    k: int = 10,
) -> float:
    """
    File-level Recall@K: Fraction of relevant FILES found in results.

    This is useful when ground truth is at file level (SWE-bench style)
    rather than chunk level.

    Args:
        retrieved_files: Ordered list of file paths from retrieval results.
        relevant_files: Set of ground-truth relevant file paths.
        k: Number of top results to consider.

    Returns:
        File recall score (0 to 1).
    """
    # Normalize path separators for cross-platform matching
    relevant_set = set(f.replace("\\", "/") for f in relevant_files)
    if not relevant_set:
        return 0.0
    top_k_files = set(f.replace("\\", "/") for f in retrieved_files[:k])
    found = len(top_k_files & relevant_set)
    return found / len(relevant_set)
