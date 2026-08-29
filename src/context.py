"""Gather repository context to feed the reasoning model.

Task 4. Currently returns a placeholder; real collection lands next.
"""

from .models import RepositoryContext


def gather_context(repo_url: str) -> RepositoryContext:
    """Collect the files a model needs to write a plausible reproduction test."""
    return RepositoryContext(
        package_json="",
        readme="",
        file_tree="",
        relevant_files=[],
    )
