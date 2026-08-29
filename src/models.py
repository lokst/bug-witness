"""Shared data models for the bug reproduction agent.

Both the Nosana (reasoning) and Daytona (execution) sides code against these,
so they can be developed in parallel.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RepositoryContext:
    """What the model gets to see about the target repository."""

    package_json: str = ""
    readme: str = ""
    file_tree: str = ""
    relevant_files: list[str] = field(default_factory=list)


@dataclass
class ReproductionPlan:
    """A hypothesis for how to reproduce the reported bug."""

    summary: str
    setup_notes: str
    test_file_name: str
    test_code: str
    expected_failure: str


@dataclass
class ExecutionResult:
    """The outcome of running a reproduction plan in a sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    reproduced: bool = False
    reason: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class AttemptEvidence:
    """A generated strategy paired with everything learned by executing it."""

    attempt: int
    plan: ReproductionPlan
    result: ExecutionResult
    artifact_notes: list[str] = field(default_factory=list)

    def as_prompt_data(self) -> dict[str, Any]:
        """Return JSON-ready evidence for a subsequent refinement request."""
        data = asdict(self)
        data["artifactNotes"] = self.artifact_notes or self.result.artifacts
        return data
