"""
Query Entry Point -- Ask questions about an ingested codebase.

This is the main interface for using GraphCodeRAG:
1. Takes a natural language question
2. Retrieves relevant code via hybrid (vector + graph) retrieval
3. Sends context + question to LLM
4. Displays the answer with source citations

Usage:
    python run_query.py --query "How does Click handle command line arguments?"
    python run_query.py --interactive
    python run_query.py --query "..." --vector-only  (baseline comparison)
"""
import argparse
import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

console = Console()


def run_query(
    query: str,
    vector_only: bool = False,
    show_context: bool = False,
    template: str = "qa",
    top_k: int = 15,
):
    """
    Run a single query against the ingested codebase.

    Args:
        query: Natural language question.
        vector_only: If True, use vector-only retrieval (baseline).
        show_context: If True, display the retrieved context chunks.
        template: Prompt template type: "qa", "explain", or "debug".
        top_k: Number of final results to use as context.
    """
    console.print(f"\n[bold cyan]Query:[/bold cyan] {query}")
    mode = "Vector-Only (Baseline)" if vector_only else "Hybrid (Vector + Graph)"
    console.print(f"[dim]Mode: {mode} | Template: {template} | Top-K: {top_k}[/dim]\n")

    # Step 1: Retrieve
    console.print("[bold]Step 1:[/bold] Retrieving relevant code...")
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever()

    if vector_only:
        results = retriever.retrieve_vector_only(query, top_k=top_k)
    else:
        results = retriever.retrieve(query, final_top_k=top_k)

    if not results:
        console.print("[red]No relevant code found. Make sure you've run ingestion first.[/red]")
        retriever.close()
        return

    # Count sources
    sources = {}
    for r in results:
        sources[r.source] = sources.get(r.source, 0) + 1
    source_str = ", ".join(f"{k}: {v}" for k, v in sorted(sources.items()))
    console.print(f"  Found [cyan]{len(results)}[/cyan] chunks ({source_str})\n")

    # Show context if requested
    if show_context:
        _display_context(results)

    # Step 2: Generate
    console.print("[bold]Step 2:[/bold] Generating answer with LLM...")
    from graphcoderag.generation.generator import LLMGenerator

    try:
        generator = LLMGenerator()
        if not generator.test_connection():
            backend = "Ollama (run `ollama serve`)" if generator.use_local else "Anthropic API"
            console.print(f"[red]Cannot connect to LLM backend: {backend}[/red]")
            console.print("[yellow]Showing retrieved context only:[/yellow]\n")
            _display_context(results)
            retriever.close()
            return

        console.print(f"  Using: [cyan]{generator.model}[/cyan] ({'local' if generator.use_local else 'cloud'})")
        answer = generator.generate(
            query=query,
            context_chunks=results,
            template=template,
            max_context_chunks=min(top_k, 10),  # Don't overwhelm the LLM
        )

        # Display answer
        console.print()
        console.print(Panel(
            Markdown(answer),
            title="[bold green]GraphCodeRAG Answer[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))

        # Show source files referenced
        files = sorted(set(r.file_path for r in results if r.file_path))
        console.print(f"\n[dim]Source files: {', '.join(files[:10])}[/dim]")

    except Exception as e:
        console.print(f"[red]Generation error: {e}[/red]")
        console.print("[yellow]Showing retrieved context instead:[/yellow]\n")
        _display_context(results)

    retriever.close()


def run_interactive():
    """Run an interactive REPL for asking questions."""
    console.print(Panel(
        "[bold]GraphCodeRAG Interactive Mode[/bold]\n\n"
        "Ask questions about the ingested codebase.\n"
        "Commands:\n"
        "  [cyan]/context[/cyan]  - Toggle showing retrieved context\n"
        "  [cyan]/vector[/cyan]   - Switch to vector-only mode\n"
        "  [cyan]/hybrid[/cyan]   - Switch to hybrid mode (default)\n"
        "  [cyan]/explain[/cyan]  - Use explain template\n"
        "  [cyan]/debug[/cyan]    - Use debug template\n"
        "  [cyan]/qa[/cyan]       - Use Q&A template (default)\n"
        "  [cyan]/quit[/cyan]     - Exit",
        title="[bold green]GraphCodeRAG[/bold green]",
        border_style="green",
    ))

    vector_only = False
    show_context = False
    template = "qa"

    while True:
        try:
            query = console.input("\n[bold cyan]> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not query:
            continue

        # Handle commands
        if query.startswith("/"):
            cmd = query.lower()
            if cmd == "/quit" or cmd == "/exit":
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "/context":
                show_context = not show_context
                console.print(f"  Context display: {'ON' if show_context else 'OFF'}")
            elif cmd == "/vector":
                vector_only = True
                console.print("  Mode: Vector-Only (Baseline)")
            elif cmd == "/hybrid":
                vector_only = False
                console.print("  Mode: Hybrid (Vector + Graph)")
            elif cmd in ("/explain", "/debug", "/qa"):
                template = cmd[1:]
                console.print(f"  Template: {template}")
            else:
                console.print(f"  [yellow]Unknown command: {cmd}[/yellow]")
            continue

        # Run the query
        run_query(
            query=query,
            vector_only=vector_only,
            show_context=show_context,
            template=template,
        )


def _display_context(results: list):
    """Display retrieved context chunks in a table."""
    table = Table(title="Retrieved Context")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("File", style="green")
    table.add_column("Lines", style="dim")
    table.add_column("Type", style="yellow")
    table.add_column("Source", style="magenta")
    table.add_column("Score", justify="right", style="bold")

    for i, r in enumerate(results, 1):
        name = getattr(r, 'display_name', None) or getattr(r, 'name', '?')
        table.add_row(
            str(i),
            name[:30],
            getattr(r, 'file_path', '?'),
            f"{getattr(r, 'start_line', 0)}-{getattr(r, 'end_line', 0)}",
            getattr(r, 'chunk_type', '?'),
            getattr(r, 'source', '?'),
            f"{getattr(r, 'score', 0.0):.4f}",
        )

    console.print(table)
    console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphCodeRAG Query Interface")
    parser.add_argument("--query", "-q", type=str, help="Question to ask about the codebase")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive REPL")
    parser.add_argument("--vector-only", action="store_true", help="Use vector-only retrieval (baseline)")
    parser.add_argument("--show-context", "-c", action="store_true", help="Display retrieved context")
    parser.add_argument("--template", "-t", choices=["qa", "explain", "debug"], default="qa",
                        help="Prompt template type")
    parser.add_argument("--top-k", type=int, default=15, help="Number of context chunks")
    args = parser.parse_args()

    if args.interactive:
        run_interactive()
    elif args.query:
        run_query(
            query=args.query,
            vector_only=args.vector_only,
            show_context=args.show_context,
            template=args.template,
            top_k=args.top_k,
        )
    else:
        console.print("[red]Error: Provide --query or --interactive[/red]")
        sys.exit(1)
