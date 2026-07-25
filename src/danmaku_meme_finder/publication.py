"""Publish only curated public JSON files after a local review session."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(project_root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail or result.returncode}")
    return result


def publish_curated_data(project_root: Path, files: list[Path], added_count: int) -> str | None:
    """Commit and push explicitly named public files, leaving other edits alone."""
    root = project_root.resolve()
    if not (root / ".git").exists():
        raise RuntimeError(f"not a Git repository: {root}")
    relative_files: list[str] = []
    for path in files:
        try:
            relative_files.append(str(path.resolve().relative_to(root)))
        except ValueError as exc:
            raise ValueError(f"publish path must be inside the project: {path}") from exc
    _git(root, ["add", "--", *relative_files])

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=root, text=True, capture_output=True, check=False
    )
    if staged.returncode == 0:
        return None
    if staged.returncode != 1:
        detail = (staged.stderr or staged.stdout).strip()
        raise RuntimeError(f"could not inspect staged Git changes: {detail or staged.returncode}")

    message = f"Curate {added_count} meme candidates" if added_count else "Update curated meme tags"
    _git(root, ["commit", "-m", message])
    branch = _git(root, ["branch", "--show-current"]).stdout.strip()
    if not branch:
        raise RuntimeError("cannot publish a detached Git HEAD")
    _git(root, ["push", "origin", branch])
    return message
