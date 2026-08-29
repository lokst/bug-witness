"""Reproduction test generation and refinement.

Task 3. The model reads the issue, the repository context and the evidence
from previous attempts, and returns a Playwright reproduction hypothesis.

Mocked for now so the orchestrator loop can be built and demoed end to end.
"""

from .models import ExecutionResult, ReproductionPlan, RepositoryContext

FIRST_ATTEMPT_TEST = """\
import { test, expect } from '@playwright/test';

test('changing a user role persists after reload', async ({ page }) => {
  await page.goto('/users');
  await page.getByRole('link', { name: 'Ada Lovelace' }).click();
  await page.getByLabel('Role').selectOption('Editor');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.reload();
  await expect(page.getByTestId('user-role')).toHaveText('Editor');
});
"""

REFINED_TEST = """\
import { test, expect } from '@playwright/test';

test('changing a user role persists in the users list', async ({ page }) => {
  await page.goto('/users');
  await page.getByRole('link', { name: 'Ada Lovelace' }).click();
  await page.getByLabel('Role').selectOption('Editor');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.getByRole('link', { name: 'Back to users' }).click();
  await expect(page.getByTestId('user-row-ada').getByTestId('role')).toHaveText('Editor');
});
"""


def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_results: list[ExecutionResult],
) -> ReproductionPlan:
    """Generate a reproduction plan, refining it against previous evidence."""
    if not previous_results:
        return ReproductionPlan(
            summary="Verify the saved role survives a full page reload.",
            setup_notes="Start the app and seed at least one user.",
            test_file_name="reproduce.spec.ts",
            test_code=FIRST_ATTEMPT_TEST,
            expected_failure="Role shows Viewer after saving Editor.",
        )

    return ReproductionPlan(
        summary=(
            "A full reload re-fetches the user, so it hides the bug. "
            "Navigate back to the users list instead, which reads from "
            "cached list state."
        ),
        setup_notes="Start the app and seed at least one user.",
        test_file_name="reproduce.spec.ts",
        test_code=REFINED_TEST,
        expected_failure="Users list still shows Viewer after saving Editor.",
    )
