"""Gather repository context to feed the reasoning model.

Task 4. Shallow-clones the repository at a pinned revision, then collects the
files that help a model write a plausible reproduction test: the manifest, the
README, a file tree, and the source files most related to the issue text.

The revision matters. Demo repositories get fixed upstream, so a run that does
not pin is not reproducible.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import RepositoryContext

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".cache",
    "__pycache__",
    ".venv",
    "venv",
}

SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".mjs", ".cjs"}

# Words too common in code to say anything about relevance.
STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "when", "then", "than",
    "have", "has", "not", "but", "are", "was", "were", "will", "would", "should",
    "user", "users", "page", "form", "should", "after", "still", "only", "does",
    "into", "over", "under", "each", "some", "any", "all", "can", "cannot",
}

MAX_FILES = 6
MAX_FILE_CHARS = 4000
MAX_TOTAL_CHARS = 24000


def _run(args: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout, raising with stderr on failure."""
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def clone_repository(repo_url: str, destination: Path, ref: str | None = None) -> Path:
    """Clone a repository, checking out a specific revision when given.

    A pinned ref needs full history, since a shallow clone only fetches the
    default branch tip.
    """
    if ref:
        _run(["git", "clone", "--quiet", repo_url, str(destination)])
        _run(["git", "checkout", "--quiet", ref], cwd=destination)
    else:
        _run(
            ["git", "clone", "--quiet", "--depth", "1", repo_url, str(destination)]
        )
    return destination


def _walk(root: Path) -> list[Path]:
    """List tracked-looking files, skipping dependency and build directories."""
    files = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def build_file_tree(root: Path, files: list[Path]) -> str:
    """Render the repository layout as relative paths, one per line."""
    return "\n".join(str(path.relative_to(root)) for path in files)


def _read(path: Path, limit: int = MAX_FILE_CHARS) -> str:
    """Read a file as text, truncating it and ignoring anything undecodable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > limit:
        return text[:limit] + "\n... truncated ...\n"
    return text


def _keywords(issue: str) -> set[str]:
    """Pull the distinctive words out of an issue description."""
    words = re.findall(r"[a-zA-Z]{3,}", issue.lower())
    return {word for word in words if word not in STOPWORDS}


def _score(path: Path, root: Path, keywords: set[str]) -> int:
    """Rank a source file by how much it overlaps with the issue wording.

    The path is weighted more heavily than the contents, since a file named
    after the feature in the issue is usually the one worth reading.
    """
    relative = str(path.relative_to(root)).lower()
    score = sum(3 for word in keywords if word in relative)

    text = _read(path).lower()
    score += sum(1 for word in keywords if word in text)
    return score


def select_relevant_files(
    root: Path,
    files: list[Path],
    issue: str,
    max_files: int = MAX_FILES,
) -> list[Path]:
    """Pick the source files most likely to explain the reported behaviour."""
    keywords = _keywords(issue)
    if not keywords:
        return []

    candidates = [path for path in files if path.suffix in SOURCE_SUFFIXES]
    ranked = sorted(
        ((_score(path, root, keywords), path) for path in candidates),
        key=lambda pair: (-pair[0], str(pair[1])),
    )
    return [path for score, path in ranked[:max_files] if score > 0]


def gather_context(
    repo_url: str,
    issue: str = "",
    ref: str | None = None,
    workdir: Path | None = None,
) -> RepositoryContext:
    """Collect the repository information a model needs to write a test.

    Clones into a temporary directory unless an existing checkout is given.
    """
    temporary = None
    if workdir is None:
        temporary = tempfile.mkdtemp(prefix="reproagent-")
        root = clone_repository(repo_url, Path(temporary) / "repo", ref)
    else:
        root = workdir

    try:
        files = _walk(root)

        package_json = ""
        manifest = root / "package.json"
        if manifest.is_file():
            package_json = _read(manifest)

        readme = ""
        for name in ("README.md", "readme.md", "README"):
            candidate = root / name
            if candidate.is_file():
                readme = _read(candidate)
                break

        relevant = []
        budget = MAX_TOTAL_CHARS
        for path in select_relevant_files(root, files, issue):
            body = _read(path)
            if len(body) > budget:
                break
            budget -= len(body)
            relevant.append(f"--- {path.relative_to(root)} ---\n{body}")

        return RepositoryContext(
            package_json=package_json,
            readme=readme,
            file_tree=build_file_tree(root, files),
            relevant_files=relevant,
        )
    finally:
        if temporary:
            shutil.rmtree(temporary, ignore_errors=True)
