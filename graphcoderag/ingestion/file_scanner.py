"""
File Scanner — Recursively finds all Python (.py) files in a repository.

Responsibilities:
- Walk directory tree
- Filter out excluded dirs (__pycache__, .git, venv, etc.)
- Filter out excluded files (setup.py, conftest.py, __init__.py)
- Optionally include/exclude test files
- Return list of FileInfo objects with path and size metadata

Usage:
    from graphcoderag.ingestion.file_scanner import scan_repository
    files = scan_repository("/path/to/repo")
    # Returns: [FileInfo(abs_path=..., rel_path=..., size_bytes=...), ...]
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List
from graphcoderag.config import EXCLUDED_DIRS, EXCLUDED_FILES, INCLUDE_TEST_FILES


@dataclass
class FileInfo:
    """Metadata about a discovered Python file."""
    abs_path: str          # Absolute path to the file
    rel_path: str          # Path relative to the repo root
    size_bytes: int        # File size in bytes


def scan_repository(repo_path: str) -> List[FileInfo]:
    """
    Recursively scan a repository for Python files.

    Args:
        repo_path: Absolute path to the repository root directory.

    Returns:
        List of FileInfo objects for each discovered Python file.

    Raises:
        FileNotFoundError: If repo_path does not exist.
        ValueError: If repo_path is not a directory.
    """
    repo = Path(repo_path)
    if not repo.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")
    if not repo.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo_path}")

    files: List[FileInfo] = []

    for py_file in repo.rglob("*.py"):
        # Skip excluded directories
        if any(excluded in py_file.parts for excluded in EXCLUDED_DIRS):
            continue

        # Skip excluded files
        if py_file.name in EXCLUDED_FILES:
            continue

        # Optionally skip test files
        if not INCLUDE_TEST_FILES and (
            py_file.name.startswith("test_") or py_file.name.endswith("_test.py")
        ):
            continue

        files.append(FileInfo(
            abs_path=str(py_file.resolve()),
            rel_path=str(py_file.relative_to(repo)),
            size_bytes=py_file.stat().st_size,
        ))

    # Sort by relative path for deterministic ordering
    files.sort(key=lambda f: f.rel_path)
    return files
