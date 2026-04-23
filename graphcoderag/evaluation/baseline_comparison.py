"""
Baseline Comparison -- Compares GraphCodeRAG (hybrid) vs standard RAG (vector-only).

The baseline uses:
- Same embedding model (all-MiniLM-L6-v2)
- Same vector store (ChromaDB)
- Same LLM (Claude / Ollama)
- Same prompts
- ONLY difference: vector-only retrieval (no graph traversal)

This isolates the impact of the graph component.

Usage:
    from graphcoderag.evaluation.baseline_comparison import BaselineComparison
    comparison = BaselineComparison()
    results = comparison.run_comparison(test_cases)
"""
from typing import List, Dict, Any
from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
from graphcoderag.generation.generator import LLMGenerator
from graphcoderag.evaluation.metrics import (
    compute_mrr, compute_recall_at_k, compute_precision_at_k,
    compute_hit_rate_at_k, compute_ndcg_at_k, compute_file_recall_at_k,
)


class BaselineComparison:
    """Compares hybrid (vector + graph) vs vector-only retrieval."""

    def __init__(self):
        self.retriever = HybridRetriever()
        self.generator = LLMGenerator()

    def run_comparison(
        self,
        test_cases: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Run both systems on each test case and compute aggregate metrics.

        Args:
            test_cases: List of dicts with keys:
                - 'question': The question string
                - 'relevant_files': List of file paths considered relevant
                - 'relevant_chunk_ids': (Optional) List of relevant chunk IDs
                - 'reference_answer': (Optional) Reference answer for LLM judge
            top_k: Number of results to evaluate at.

        Returns:
            Dict with aggregate metrics for both systems and per-case details.
        """
        hybrid_metrics = []
        baseline_metrics = []
        per_case_results = []

        for i, case in enumerate(test_cases):
            question = case["question"]
            relevant_files = set(case.get("relevant_files", []))
            relevant_ids = set(case.get("relevant_chunk_ids", []))

            # Run hybrid retrieval
            hybrid_results = self.retriever.retrieve(question, final_top_k=top_k)
            # Run vector-only retrieval
            baseline_results = self.retriever.retrieve_vector_only(question, top_k=top_k)

            # Extract IDs and file paths
            hybrid_ids = [r.chunk_id for r in hybrid_results]
            baseline_ids = [r.chunk_id for r in baseline_results]
            hybrid_files = [r.file_path for r in hybrid_results]
            baseline_files = [r.file_path for r in baseline_results]

            # Compute file-level metrics (always available)
            h_file_metrics = self._compute_file_metrics(hybrid_files, relevant_files, top_k)
            b_file_metrics = self._compute_file_metrics(baseline_files, relevant_files, top_k)

            # Compute chunk-level metrics (if ground truth IDs available)
            if relevant_ids:
                h_chunk_metrics = self._compute_chunk_metrics(hybrid_ids, relevant_ids, top_k)
                b_chunk_metrics = self._compute_chunk_metrics(baseline_ids, relevant_ids, top_k)
            else:
                h_chunk_metrics = {}
                b_chunk_metrics = {}

            hybrid_entry = {**h_file_metrics, **h_chunk_metrics}
            baseline_entry = {**b_file_metrics, **b_chunk_metrics}
            hybrid_metrics.append(hybrid_entry)
            baseline_metrics.append(baseline_entry)

            # Count sources in hybrid results
            sources = {}
            for r in hybrid_results:
                sources[r.source] = sources.get(r.source, 0) + 1

            per_case_results.append({
                "question": question,
                "hybrid_files": list(set(hybrid_files)),
                "baseline_files": list(set(baseline_files)),
                "new_files_from_graph": list(set(hybrid_files) - set(baseline_files)),
                "hybrid_sources": sources,
                "hybrid_metrics": hybrid_entry,
                "baseline_metrics": baseline_entry,
                # Cache retrieval results for reuse by run_with_generation()
                "_hybrid_results": hybrid_results,
                "_baseline_results": baseline_results,
            })

        # Aggregate metrics
        aggregate_hybrid = self._aggregate_metrics(hybrid_metrics)
        aggregate_baseline = self._aggregate_metrics(baseline_metrics)

        # Compute deltas
        deltas = {}
        for key in aggregate_hybrid:
            deltas[key] = round(aggregate_hybrid[key] - aggregate_baseline[key], 4)

        return {
            "hybrid_aggregate": aggregate_hybrid,
            "baseline_aggregate": aggregate_baseline,
            "deltas": deltas,
            "per_case": per_case_results,
            "num_cases": len(test_cases),
            "top_k": top_k,
        }

    def run_with_generation(
        self,
        test_cases: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Run comparison WITH LLM generation and LLM judge scoring.
        More expensive (2 LLM calls per test case + 2 judge calls) but gives
        end-to-end quality assessment.
        """
        from graphcoderag.evaluation.llm_judge import LLMJudge
        judge = LLMJudge(self.generator)

        results = self.run_comparison(test_cases, top_k)

        for case_result in results["per_case"]:
            question = case_result["question"]

            # Reuse cached retrieval results (no double retrieval!)
            hybrid_results = case_result.pop("_hybrid_results", [])
            baseline_results = case_result.pop("_baseline_results", [])

            hybrid_answer = self.generator.generate(question, hybrid_results)
            baseline_answer = self.generator.generate(question, baseline_results)

            # Get reference answer if available
            ref = next(
                (tc.get("reference_answer", "") for tc in test_cases
                 if tc["question"] == question), ""
            )

            # Judge both answers — use each system's OWN files as context
            hybrid_ctx = f"Files: {', '.join(case_result['hybrid_files'][:5])}"
            baseline_ctx = f"Files: {', '.join(case_result['baseline_files'][:5])}"

            hybrid_scores = judge.rate_answer(question, hybrid_answer, hybrid_ctx, ref)
            baseline_scores = judge.rate_answer(question, baseline_answer, baseline_ctx, ref)

            case_result["hybrid_answer"] = hybrid_answer[:500]
            case_result["baseline_answer"] = baseline_answer[:500]
            case_result["hybrid_judge_scores"] = hybrid_scores
            case_result["baseline_judge_scores"] = baseline_scores

        # Aggregate judge scores
        hybrid_judge_avg = self._avg_judge_scores(
            [c.get("hybrid_judge_scores", {}) for c in results["per_case"]]
        )
        baseline_judge_avg = self._avg_judge_scores(
            [c.get("baseline_judge_scores", {}) for c in results["per_case"]]
        )
        results["hybrid_judge_avg"] = hybrid_judge_avg
        results["baseline_judge_avg"] = baseline_judge_avg

        return results

    def _compute_file_metrics(
        self, retrieved_files: List[str], relevant_files: set, k: int
    ) -> Dict[str, float]:
        """Compute file-level retrieval metrics."""
        if not relevant_files:
            return {"file_recall": 0.0, "file_hit_rate": 0.0}
        # Normalize paths for cross-platform matching
        norm_retrieved = [f.replace("\\", "/") for f in retrieved_files]
        norm_relevant = set(f.replace("\\", "/") for f in relevant_files)
        return {
            "file_recall": compute_file_recall_at_k(norm_retrieved, norm_relevant, k),
            "file_hit_rate": compute_hit_rate_at_k(norm_retrieved, norm_relevant, k),
        }

    def _compute_chunk_metrics(
        self, retrieved_ids: List[str], relevant_ids: set, k: int
    ) -> Dict[str, float]:
        """Compute chunk-level retrieval metrics."""
        return {
            "mrr": compute_mrr(retrieved_ids, relevant_ids),
            "recall": compute_recall_at_k(retrieved_ids, relevant_ids, k),
            "precision": compute_precision_at_k(retrieved_ids, relevant_ids, k),
            "hit_rate": compute_hit_rate_at_k(retrieved_ids, relevant_ids, k),
            "ndcg": compute_ndcg_at_k(retrieved_ids, relevant_ids, k),
        }

    def _aggregate_metrics(self, metrics_list: List[Dict[str, float]]) -> Dict[str, float]:
        """Average metrics across all test cases."""
        if not metrics_list:
            return {}
        all_keys = set()
        for m in metrics_list:
            all_keys.update(m.keys())

        aggregated = {}
        for key in sorted(all_keys):
            values = [m.get(key, 0.0) for m in metrics_list]
            aggregated[key] = round(sum(values) / len(values), 4)
        return aggregated

    def _avg_judge_scores(self, scores_list: List[Dict]) -> Dict[str, float]:
        """Average LLM judge scores."""
        keys = ["accuracy", "completeness", "helpfulness", "avg_score"]
        result = {}
        valid = [s for s in scores_list if s.get("avg_score", 0) > 0]
        if not valid:
            return {k: 0.0 for k in keys}
        for k in keys:
            vals = [s.get(k, 0) for s in valid]
            result[k] = round(sum(vals) / len(vals), 2)
        return result

    def close(self):
        """Close underlying connections."""
        self.retriever.close()
