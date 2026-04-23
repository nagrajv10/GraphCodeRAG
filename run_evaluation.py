"""
Evaluation Entry Point -- Compare GraphCodeRAG (Hybrid) vs Baseline (Vector-only).

Runs both retrieval systems on a set of test cases and computes:
- File-level Recall@K: How many relevant files were retrieved
- Hit Rate@K: At least one relevant file found
- (Optional) LLM Judge scores: Accuracy, Completeness, Helpfulness

Usage:
    python run_evaluation.py                          # Retrieval metrics only
    python run_evaluation.py --with-generation        # + LLM judge scoring
    python run_evaluation.py --top-k 15               # Custom K value
"""
import json
import csv
import sys
import os
import argparse
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def load_test_cases(path: str = "data/swebench/test_cases.json") -> list:
    """Load test cases from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_evaluation(
    test_cases_path: str = "data/swebench/test_cases.json",
    top_k: int = 10,
    with_generation: bool = False,
    output_csv: str = "data/evaluation_results.csv",
):
    """Run the full evaluation pipeline."""
    console.print(Panel(
        "[bold]GraphCodeRAG Evaluation Pipeline[/bold]\n"
        "Comparing Hybrid (Vector + Graph) vs Baseline (Vector-only)",
        title="[bold green]Phase 5: Evaluation[/bold green]",
        border_style="green",
    ))

    # Load test cases
    console.print(f"\n[bold]Loading test cases from:[/bold] {test_cases_path}")
    test_cases = load_test_cases(test_cases_path)
    console.print(f"  Found [cyan]{len(test_cases)}[/cyan] test cases\n")

    # Run comparison
    from graphcoderag.evaluation.baseline_comparison import BaselineComparison
    comparison = BaselineComparison()

    if with_generation:
        console.print("[bold]Running with LLM generation + judge scoring...[/bold]")
        console.print("[dim](This will make LLM calls for each test case)[/dim]\n")
        results = comparison.run_with_generation(test_cases, top_k=top_k)
    else:
        console.print("[bold]Running retrieval-only evaluation...[/bold]\n")
        results = comparison.run_comparison(test_cases, top_k=top_k)

    # Display per-case results
    _display_per_case_results(results, with_generation)

    # Display aggregate metrics
    _display_aggregate_results(results, with_generation)

    # Save results to CSV
    _save_results_csv(results, output_csv, with_generation)
    console.print(f"\n[dim]Results saved to: {output_csv}[/dim]")

    comparison.close()
    console.print("\n[bold green]Evaluation complete![/bold green]\n")


def _display_per_case_results(results: dict, with_generation: bool):
    """Display per-case comparison table."""
    table = Table(title=f"Per-Case Results (top_k={results['top_k']})")
    table.add_column("#", style="dim", width=3)
    table.add_column("Question", style="cyan", max_width=40)
    table.add_column("Hybrid Files", justify="right")
    table.add_column("Baseline Files", justify="right")
    table.add_column("+Graph Files", style="green", justify="right")
    table.add_column("H-Recall", style="bold", justify="right")
    table.add_column("B-Recall", justify="right")

    if with_generation:
        table.add_column("H-Judge", style="bold", justify="right")
        table.add_column("B-Judge", justify="right")

    for i, case in enumerate(results["per_case"], 1):
        h_recall = f"{case['hybrid_metrics'].get('file_recall', 0):.2f}"
        b_recall = f"{case['baseline_metrics'].get('file_recall', 0):.2f}"
        new_files = len(case.get("new_files_from_graph", []))

        row = [
            str(i),
            case["question"][:40],
            str(len(set(case["hybrid_files"]))),
            str(len(set(case["baseline_files"]))),
            f"+{new_files}" if new_files > 0 else "-",
            h_recall,
            b_recall,
        ]

        if with_generation:
            h_judge = case.get("hybrid_judge_scores", {}).get("avg_score", 0)
            b_judge = case.get("baseline_judge_scores", {}).get("avg_score", 0)
            row.append(f"{h_judge:.1f}")
            row.append(f"{b_judge:.1f}")

        table.add_row(*row)

    console.print(table)


def _display_aggregate_results(results: dict, with_generation: bool):
    """Display the aggregate comparison table."""
    console.print()

    # Main metrics table
    table = Table(title="Aggregate Metrics Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Hybrid (Ours)", style="bold green", justify="right")
    table.add_column("Baseline", justify="right")
    table.add_column("Delta", justify="right")

    hybrid = results["hybrid_aggregate"]
    baseline = results["baseline_aggregate"]
    deltas = results["deltas"]

    for metric in sorted(hybrid.keys()):
        h_val = hybrid.get(metric, 0)
        b_val = baseline.get(metric, 0)
        d_val = deltas.get(metric, 0)

        # Color delta based on sign
        if d_val > 0:
            delta_str = f"[green]+{d_val:.4f}[/green]"
        elif d_val < 0:
            delta_str = f"[red]{d_val:.4f}[/red]"
        else:
            delta_str = f"{d_val:.4f}"

        table.add_row(metric, f"{h_val:.4f}", f"{b_val:.4f}", delta_str)

    console.print(table)

    # LLM Judge results (if available)
    if with_generation and "hybrid_judge_avg" in results:
        console.print()
        judge_table = Table(title="LLM Judge Scores (1-5 scale)")
        judge_table.add_column("Dimension", style="cyan")
        judge_table.add_column("Hybrid (Ours)", style="bold green", justify="right")
        judge_table.add_column("Baseline", justify="right")

        h_judge = results.get("hybrid_judge_avg", {})
        b_judge = results.get("baseline_judge_avg", {})

        for dim in ["accuracy", "completeness", "helpfulness", "avg_score"]:
            judge_table.add_row(
                dim.title(),
                f"{h_judge.get(dim, 0):.2f}",
                f"{b_judge.get(dim, 0):.2f}",
            )
        console.print(judge_table)

    # Summary verdict
    improvement = deltas.get("file_recall", 0)
    if improvement > 0:
        console.print(Panel(
            f"[bold green]GraphCodeRAG outperforms baseline![/bold green]\n"
            f"File Recall improvement: +{improvement:.4f} ({improvement*100:.1f}%)",
            title="Verdict",
            border_style="green",
        ))
    elif improvement == 0:
        console.print(Panel(
            "[bold yellow]Results are tied on File Recall.[/bold yellow]\n"
            "The graph may add value on other metrics or specific queries.",
            title="Verdict",
            border_style="yellow",
        ))
    else:
        console.print(Panel(
            f"[bold red]Baseline outperforms on File Recall: {improvement:.4f}[/bold red]\n"
            "This may indicate the graph is adding noise. Consider tuning weights.",
            title="Verdict",
            border_style="red",
        ))


def _save_results_csv(results: dict, output_path: str, with_generation: bool):
    """Save evaluation results to CSV."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    rows = []
    for i, case in enumerate(results["per_case"], 1):
        row = {
            "case_num": i,
            "question": case["question"],
            "hybrid_file_recall": case["hybrid_metrics"].get("file_recall", 0),
            "baseline_file_recall": case["baseline_metrics"].get("file_recall", 0),
            "hybrid_hit_rate": case["hybrid_metrics"].get("file_hit_rate", 0),
            "baseline_hit_rate": case["baseline_metrics"].get("file_hit_rate", 0),
            "new_files_from_graph": len(case.get("new_files_from_graph", [])),
            "hybrid_files": "; ".join(sorted(set(case["hybrid_files"]))),
            "baseline_files": "; ".join(sorted(set(case["baseline_files"]))),
            "timestamp": datetime.now().isoformat(),
        }

        if with_generation:
            h_judge = case.get("hybrid_judge_scores", {})
            b_judge = case.get("baseline_judge_scores", {})
            row["hybrid_judge_avg"] = h_judge.get("avg_score", 0)
            row["baseline_judge_avg"] = b_judge.get("avg_score", 0)

        rows.append(row)

    # Add aggregate row
    agg_row = {
        "case_num": "AVG",
        "question": "=== AGGREGATE ===",
        "hybrid_file_recall": results["hybrid_aggregate"].get("file_recall", 0),
        "baseline_file_recall": results["baseline_aggregate"].get("file_recall", 0),
        "hybrid_hit_rate": results["hybrid_aggregate"].get("file_hit_rate", 0),
        "baseline_hit_rate": results["baseline_aggregate"].get("file_hit_rate", 0),
        "new_files_from_graph": "",
        "hybrid_files": "",
        "baseline_files": "",
        "timestamp": datetime.now().isoformat(),
    }
    if with_generation and "hybrid_judge_avg" in results:
        agg_row["hybrid_judge_avg"] = results["hybrid_judge_avg"].get("avg_score", 0)
        agg_row["baseline_judge_avg"] = results["baseline_judge_avg"].get("avg_score", 0)
    rows.append(agg_row)

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphCodeRAG Evaluation")
    parser.add_argument("--test-cases", default="data/swebench/test_cases.json",
                        help="Path to test cases JSON")
    parser.add_argument("--top-k", type=int, default=10, help="Top-K for evaluation")
    parser.add_argument("--with-generation", action="store_true",
                        help="Also run LLM generation and judge scoring")
    parser.add_argument("--output", default="data/evaluation_results.csv",
                        help="Output CSV path")
    args = parser.parse_args()

    run_evaluation(
        test_cases_path=args.test_cases,
        top_k=args.top_k,
        with_generation=args.with_generation,
        output_csv=args.output,
    )
