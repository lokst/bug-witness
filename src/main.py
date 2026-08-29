"""CLI entry point and the reproduction loop.

Tasks 2, 7 and 8: read the issue, ask for a reproduction plan, execute it,
and retry with the evidence until the bug is reproduced or attempts run out.
"""

import argparse
import json
from pathlib import Path

from .classifier import classify
from .context import gather_context
from .daytona import run_in_daytona
from .models import ExecutionResult, ReproductionPlan
from .nosana import generate_reproduction_test

OUTPUT_DIR = Path("outputs")


def save_attempt(
    attempt: int,
    plan: ReproductionPlan,
    result: ExecutionResult,
) -> Path:
    """Write the generated test and its execution evidence to disk."""
    directory = OUTPUT_DIR / f"attempt-{attempt}"
    directory.mkdir(parents=True, exist_ok=True)

    (directory / plan.test_file_name).write_text(plan.test_code)
    (directory / "stdout.txt").write_text(result.stdout)
    (directory / "stderr.txt").write_text(result.stderr)
    (directory / "plan.json").write_text(
        json.dumps(
            {
                "summary": plan.summary,
                "setupNotes": plan.setup_notes,
                "testFileName": plan.test_file_name,
                "expectedFailure": plan.expected_failure,
            },
            indent=2,
        )
    )
    return directory


def print_summary(
    reproduced: bool,
    attempt: int,
    max_attempts: int,
    plan: ReproductionPlan,
    result: ExecutionResult,
    directory: Path,
) -> None:
    """Print a summary a judge can read without digging through logs."""
    print()
    if reproduced:
        print("BUG REPRODUCED")
        print(f"Attempt: {attempt}/{max_attempts}")
        print()
        print(f"Expected: {plan.expected_failure}")
        print(f"Observed: {result.reason}")
    else:
        print("UNABLE TO REPRODUCE")
        print(f"{max_attempts} reproduction strategies attempted.")
        print()
        print(f"Last attempt: {result.reason}")

    print()
    print(f"Generated test: {directory / plan.test_file_name}")


def run(repo: str, issue: str, max_attempts: int, ref: str | None = None) -> bool:
    """Drive the think, execute, reflect loop. Returns whether it reproduced."""
    print("Gathering repository context")
    context = gather_context(repo, issue=issue, ref=ref)
    print(f"  {len(context.relevant_files)} relevant files selected")
    previous_results: list[ExecutionResult] = []

    plan = None
    result = None
    directory = OUTPUT_DIR

    for attempt in range(1, max_attempts + 1):
        print(f"Attempt {attempt}/{max_attempts}: generating reproduction test")
        plan = generate_reproduction_test(issue, context, previous_results)
        print(f"  {plan.summary}")

        print(f"Attempt {attempt}/{max_attempts}: running in sandbox")
        result = classify(run_in_daytona(repo, plan, attempt=attempt))
        print(f"  {result.reason}")

        directory = save_attempt(attempt, plan, result)

        if result.reproduced:
            print_summary(True, attempt, max_attempts, plan, result, directory)
            return True

        previous_results.append(result)

    print_summary(False, max_attempts, max_attempts, plan, result, directory)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a natural-language bug report into a reproduction test."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository URL")
    parser.add_argument(
        "--issue", required=True, help="Path to a file containing the issue text"
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Commit or tag to pin the repository to. Recommended: default "
        "branches move, and a moved branch may no longer contain the bug.",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    issue = Path(args.issue).read_text()
    reproduced = run(args.repo, issue, args.max_attempts, ref=args.ref)
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
