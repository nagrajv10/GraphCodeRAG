"""
Ingestion Pipeline Entry Point -- Scans a repo, parses files, creates chunks,
extracts dependencies, stores in vector DB and graph DB.

Usage:
    python run_ingestion.py --repo-path data/repos/my_repo
    python run_ingestion.py --repo-url https://github.com/user/repo
    python run_ingestion.py --repo-url https://github.com/user/repo --skip-graph
"""
import argparse
import sys
import subprocess
from pathlib import Path
from typing import List
from rich.console import Console
from rich.progress import track
from rich.table import Table

from graphcoderag.config import REPOS_DIR
from graphcoderag.ingestion.file_scanner import scan_repository
from graphcoderag.ingestion.ast_parser import PythonASTParser
from graphcoderag.ingestion.code_chunker import CodeChunker, CodeChunk
from graphcoderag.ingestion.dependency_extractor import DependencyExtractor, DependencyEdge

console = Console()


def clone_repo(repo_url: str) -> Path:
    """Clone a GitHub repository into data/repos/."""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    target = REPOS_DIR / repo_name
    if target.exists():
        console.print(f"[yellow]Repository already exists at {target}, skipping clone.[/yellow]")
        return target
    console.print(f"[blue]Cloning {repo_url} into {target}...[/blue]")
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target)], check=True)
    return target


def run_ingestion(
    repo_path: str,
    skip_graph: bool = False,
    skip_vector: bool = False,
) -> List[CodeChunk]:
    """Run the full ingestion pipeline on a repository."""
    console.print(f"\n[bold green]{'=' * 55}[/bold green]")
    console.print(f"[bold green]  GraphCodeRAG Ingestion Pipeline[/bold green]")
    console.print(f"[bold green]{'=' * 55}[/bold green]\n")
    console.print(f"[dim]Repository: {repo_path}[/dim]\n")

    # Step 1: Scan for Python files
    console.print("[bold]Step 1/4:[/bold] Scanning for Python files...")
    files = scan_repository(repo_path)
    console.print(f"  Found [cyan]{len(files)}[/cyan] Python files\n")

    if not files:
        console.print("[red]No Python files found! Check the repo path.[/red]")
        return []

    # Step 2: Parse each file, create chunks, extract dependencies
    console.print("[bold]Step 2/4:[/bold] Parsing files with Tree-sitter & chunking...")
    parser = PythonASTParser()
    chunker = CodeChunker()
    dep_extractor = DependencyExtractor()
    all_chunks: List[CodeChunk] = []
    all_edges: List[DependencyEdge] = []
    parse_errors = 0

    for file_info in track(files, description="  Parsing..."):
        try:
            tree, source_code = parser.parse_file(file_info.abs_path)

            # Extract AST nodes and create chunks
            ast_nodes = parser.extract_functions_and_classes(tree, source_code)
            chunks = chunker.chunk_file(file_info.rel_path, ast_nodes, source_code)
            all_chunks.extend(chunks)

            # Extract dependency edges
            edges = dep_extractor.extract_from_file(tree, source_code, file_info.rel_path)
            all_edges.extend(edges)
        except Exception as e:
            parse_errors += 1
            console.print(f"  [red]Error parsing {file_info.rel_path}: {e}[/red]")

    console.print(f"  Created [cyan]{len(all_chunks)}[/cyan] chunks ({parse_errors} parse errors)")

    # Edge breakdown
    edge_counts = {}
    for e in all_edges:
        edge_counts[e.edge_type] = edge_counts.get(e.edge_type, 0) + 1
    edge_str = ", ".join(f"{k}: {v}" for k, v in sorted(edge_counts.items()))
    console.print(f"  Extracted [cyan]{len(all_edges)}[/cyan] edges ({edge_str})\n")

    # Step 3: Store in Neo4j graph
    console.print("[bold]Step 3/4:[/bold] Storing in Neo4j knowledge graph...")
    if skip_graph:
        console.print("  [yellow]Skipped (--skip-graph flag)[/yellow]\n")
    else:
        # Fix #10: try/finally ensures driver.close() is always called
        graph_store = None
        try:
            from graphcoderag.storage.graph_store import GraphStore
            graph_store = GraphStore()
            graph_store.clear()
            console.print("  Storing nodes...")
            graph_store.store_chunks(all_chunks)
            console.print("  Storing edges...")
            graph_store.store_edges(all_edges)
            stats = graph_store.get_graph_stats()
            console.print(f"  [green]Done![/green] Nodes: {stats.get('total_nodes', 0)}, "
                          f"Edges: {stats.get('total_edges', 0)}\n")
        except Exception as e:
            console.print(f"  [red]Neo4j error: {e}[/red]")
            console.print("  [yellow]Skipping graph storage. Is Neo4j running?[/yellow]\n")
        finally:
            if graph_store:
                graph_store.close()

    # Step 4: Store in Vector store
    console.print("[bold]Step 4/4:[/bold] Storing in vector store...")
    if skip_vector:
        console.print("  [yellow]Skipped (--skip-vector flag)[/yellow]\n")
    else:
        try:
            from graphcoderag.config import VECTOR_BACKEND
            if VECTOR_BACKEND == "faiss":
                from graphcoderag.storage.faiss_store import FaissVectorStore
                vector_store = FaissVectorStore()
                console.print("  Using FAISS backend...")
            else:
                from graphcoderag.storage.vector_store import VectorStore
                vector_store = VectorStore()
                console.print("  Using ChromaDB backend...")
                
            vector_store.clear()
            console.print(f"  Embedding and storing {len(all_chunks)} chunks...")
            vector_store.add_chunks(all_chunks)
            console.print(f"  [green]Done![/green] Stored {vector_store.count()} embeddings in vector store\n")
        except Exception as e:
            console.print(f"  [red]Vector store error: {e}[/red]")
            console.print(f"  [yellow]Hint: Check your OPENAI_API_KEY in .env or set USE_LOCAL_EMBEDDINGS=true[/yellow]\n")

    # === Summary ===
    func_chunks = [c for c in all_chunks if c.chunk_type == "function"]
    class_chunks = [c for c in all_chunks if c.chunk_type == "class"]
    module_chunks = [c for c in all_chunks if c.chunk_type == "module"]

    console.print(f"[bold green]{'=' * 55}[/bold green]")
    console.print(f"[bold green]  Ingestion Complete[/bold green]")
    console.print(f"[bold green]{'=' * 55}[/bold green]")

    summary_table = Table(title="Chunk Summary")
    summary_table.add_column("Type", style="cyan")
    summary_table.add_column("Count", style="green", justify="right")
    summary_table.add_row("Functions", str(len(func_chunks)))
    summary_table.add_row("Classes", str(len(class_chunks)))
    summary_table.add_row("Modules", str(len(module_chunks)))
    summary_table.add_row("[bold]Total[/bold]", f"[bold]{len(all_chunks)}[/bold]")
    console.print(summary_table)

    edge_table = Table(title="Dependency Edges")
    edge_table.add_column("Type", style="cyan")
    edge_table.add_column("Count", style="green", justify="right")
    for etype in ["IMPORTS", "CALLS", "CONTAINS", "INHERITS"]:
        edge_table.add_row(etype, str(edge_counts.get(etype, 0)))
    edge_table.add_row("[bold]Total[/bold]", f"[bold]{len(all_edges)}[/bold]")
    console.print(edge_table)

    # Show sample chunks
    if all_chunks:
        console.print("\n[bold]Sample chunks:[/bold]")
        for chunk in all_chunks[:5]:
            lines = chunk.source_code.split("\n")
            preview = lines[0][:80] if lines else ""
            console.print(
                f"  [{chunk.chunk_type}] [cyan]{chunk.display_name}[/cyan] "
                f"({chunk.file_path}:{chunk.start_line}-{chunk.end_line}) "
                f"-- {preview}..."
            )

    return all_chunks


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="GraphCodeRAG Ingestion Pipeline")
    arg_parser.add_argument("--repo-path", type=str, help="Local path to the repository")
    arg_parser.add_argument("--repo-url", type=str, help="GitHub URL to clone and ingest")
    arg_parser.add_argument("--skip-graph", action="store_true", help="Skip Neo4j storage")
    arg_parser.add_argument("--skip-vector", action="store_true", help="Skip ChromaDB storage")
    args = arg_parser.parse_args()

    if args.repo_url:
        repo_path = str(clone_repo(args.repo_url))
    elif args.repo_path:
        repo_path = args.repo_path
    else:
        console.print("[red]Error: Provide --repo-path or --repo-url[/red]")
        sys.exit(1)

    run_ingestion(repo_path, skip_graph=args.skip_graph, skip_vector=args.skip_vector)
