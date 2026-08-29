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

# The model has a large context window, so the budget is set by how much the
# ranker can usefully surface rather than by what fits. Too few files and it
# guesses at routes and form labels it never saw.
MAX_FILES = 12
MAX_FILE_CHARS = 4000
MAX_TOTAL_CHARS = 40000

# The file tree is a map, not evidence, so it gets a much smaller share of the
# prompt than the files themselves. Paths at or above this depth are listed
# individually; deeper ones collapse to a count.
MAX_TREE_CHARS = 8000
MAX_TREE_DEPTH = 3

# Almost every browser reproduction has to navigate and sign in, so the files
# defining routes and the login form are worth including whether or not the
# issue text happens to mention them.
ALWAYS_INCLUDE = ("app.jsx", "app.tsx", "login.jsx", "login.tsx", "routes.jsx")


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

    A pinned ref is fetched at depth 1 rather than cloned in full: GitHub
    serves a fetch for an arbitrary commit, so the whole history is not needed
    to check one revision out.  Not every host allows that, so a refused fetch
    falls back to a full clone.
    """
    if not ref:
        _run(["git", "clone", "--quiet", "--depth", "1", repo_url, str(destination)])
        return destination

    destination.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "--quiet"], cwd=destination)
    _run(["git", "remote", "add", "origin", repo_url], cwd=destination)
    try:
        _run(["git", "fetch", "--quiet", "--depth", "1", "origin", ref], cwd=destination)
        _run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=destination)
    except RuntimeError:
        shutil.rmtree(destination, ignore_errors=True)
        _run(["git", "clone", "--quiet", repo_url, str(destination)])
        _run(["git", "checkout", "--quiet", ref], cwd=destination)
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


def _render_tree(root: Path, files: list[Path], depth: int) -> str:
    """Render paths, collapsing anything below ``depth`` into a per-directory count."""
    lines: list[str] = []
    collapsed: dict[str, int] = {}
    for path in files:
        relative = path.relative_to(root)
        if len(relative.parts) <= depth:
            lines.append(relative.as_posix())
        else:
            parent = "/".join(relative.parts[:depth])
            collapsed[parent] = collapsed.get(parent, 0) + 1
    lines.extend(f"{parent}/ ({count} more files)" for parent, count in collapsed.items())
    return "\n".join(sorted(lines))


def build_file_tree(
    root: Path, files: list[Path], max_chars: int = MAX_TREE_CHARS
) -> str:
    """Render the repository layout within a character budget.

    The tree competes with the relevant files for the model's attention, and a
    real repository has enough paths to crowd them out: a shallow clone of
    Excalidraw renders about 66,000 characters, well over the whole
    ``MAX_TOTAL_CHARS`` budget for file contents.

    Shallow paths survive intact because they carry the layout that matters —
    where the app, the routes and the tests live.  Deeper ones collapse to a
    count, progressively, until the result fits.
    """
    tree = ""
    for depth in range(MAX_TREE_DEPTH, 0, -1):
        tree = _render_tree(root, files, depth)
        if len(tree) <= max_chars:
            return tree
    return tree[:max_chars] + "\n... truncated ...\n"


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
    selected = [path for score, path in ranked[:max_files] if score > 0]

    for path in candidates:
        if path.name.lower() in ALWAYS_INCLUDE and path not in selected:
            selected.append(path)
    return selected


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
