"""Classify a sandbox run as reproduction, or as a failure to get that far.

Task 6, owned by Person 2. This stub keeps the orchestrator loop runnable in
the meantime by trusting whatever the execution layer reported.
"""

from .models import ExecutionResult


def classify(result: ExecutionResult) -> ExecutionResult:
    """Decide whether a run actually reproduced the bug.

    A failing assertion is potential reproduction; setup, dependency and test
    syntax failures are not, and should be distinguished here.
    """
    return result
