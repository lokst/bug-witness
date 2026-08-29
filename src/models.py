"""Shared data models for the bug reproduction agent.

Both the Nosana (reasoning) and Daytona (execution) sides code against these,
so they can be developed in parallel.
"""

from dataclasses import dataclass, field


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
    # Pipeline stage the run reached: "sandbox", "repository", "setup",
    # "start" or "test". Only a "test" result can be classified as reproduced.
    stage: str = ""
