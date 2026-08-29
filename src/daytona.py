"""Sandbox execution of a reproduction plan.

Task 5, owned by Person 2. This mock mirrors the demo story so the retry loop
can be built and rehearsed before the real Daytona integration lands: the first
attempt fails to reproduce, the second one reproduces the bug.
"""

from .models import ExecutionResult, ReproductionPlan

_ATTEMPT_ONE_STDOUT = """\
Running 1 test using 1 worker

  ok 1 reproduce.spec.ts:3:1 > changing a user role persists after reload (1.4s)

  1 passed (1.9s)
"""

_ATTEMPT_TWO_STDOUT = """\
Running 1 test using 1 worker

  x 1 reproduce.spec.ts:3:1 > changing a user role persists in the users list (1.6s)

  1) reproduce.spec.ts:3:1 > changing a user role persists in the users list

    Error: expect(locator).toHaveText(expected)

    Locator: getByTestId('user-row-ada').getByTestId('role')
    Expected string: "Editor"
    Received string: "Viewer"

  1 failed (2.1s)
"""


def run_in_daytona(
    repo_url: str,
    plan: ReproductionPlan,
    setup_command: str | None = None,
    start_command: str | None = None,
    attempt: int = 1,
) -> ExecutionResult:
    """Run a reproduction plan in an isolated sandbox and report the outcome."""
    if attempt == 1:
        return ExecutionResult(
            exit_code=0,
            stdout=_ATTEMPT_ONE_STDOUT,
            stderr="",
            reproduced=False,
            reason="Test passed, so the reported behaviour did not occur.",
            artifacts=[],
        )

    return ExecutionResult(
        exit_code=1,
        stdout=_ATTEMPT_TWO_STDOUT,
        stderr="",
        reproduced=True,
        reason="Assertion failed: expected Editor, received Viewer",
        artifacts=["screenshots/users-list.png"],
    )
