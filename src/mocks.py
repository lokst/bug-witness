"""Canned responses for demoing without Nosana or Daytona.

Task 9's fallback path. These mirror the shape of a real run against the demo
repository so the loop can be rehearsed when the network, the deployment, or a
sandbox is unavailable.
"""

from .models import ExecutionResult, ReproductionPlan, RepositoryContext

_NAIVE_TEST = """\
const { test, expect } = require('@playwright/test');

test('shows an error when campaign creation fails', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username or Email').fill('testuser');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.goto('/campaigns/new');
  await page.getByLabel('Campaign Title').fill('Playwright campaign');
  await page.getByLabel('Description').fill('A sufficiently long description.');
  await page.getByLabel('Goal Amount ($)').fill('100');
  await page.getByRole('button', { name: 'Create Campaign' }).click();

  await expect(page.getByRole('alert')).toBeVisible();
});
"""

_INTERCEPTING_TEST = """\
const { test, expect } = require('@playwright/test');

test('shows the API error when campaign creation fails', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username or Email').fill('testuser');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\\/dashboard$/);

  await page.route('**/api/campaigns', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Service temporarily unavailable' }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto('/campaigns/new');
  await page.getByLabel('Campaign Title').fill('Playwright campaign');
  await page.getByLabel('Description').fill('A sufficiently long description.');
  await page.getByLabel('Goal Amount ($)').fill('100');
  await page.getByRole('button', { name: 'Create Campaign' }).click();

  await expect(
    page.getByText('Service temporarily unavailable', { exact: true }),
  ).toBeVisible();
});
"""

_ATTEMPT_ONE_STDOUT = """\
Running 1 test using 1 worker

  ok 1 reproduce.spec.js:3:1 > shows an error when campaign creation fails (2.1s)

  1 passed (2.6s)
"""

_ATTEMPT_TWO_STDOUT = """\
Running 1 test using 1 worker

  x 1 reproduce.spec.js:3:1 > shows the API error when campaign creation fails

  1) reproduce.spec.js:3:1 > shows the API error when campaign creation fails

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('Service temporarily unavailable', { exact: true })
    Expected: visible
    Received: element(s) not found

      28 |   await expect(
    > 29 |     page.getByText('Service temporarily unavailable', { exact: true }),
         |     ^
      30 |   ).toBeVisible();

  1 failed (32.4s)
"""


def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_results: list[ExecutionResult],
) -> ReproductionPlan:
    """Return a canned plan, refined once evidence exists."""
    if not previous_results:
        return ReproductionPlan(
            summary="Submit the campaign form and expect a visible error.",
            setup_notes="Seed the database and sign in as testuser.",
            test_file_name="reproduce.spec.js",
            test_code=_NAIVE_TEST,
            expected_failure="No error message is shown after a failed save.",
        )

    return ReproductionPlan(
        summary=(
            "The first attempt submitted against a healthy server, so creation "
            "succeeded and there was no error to display. Intercept the request "
            "and return a 503 so the failure path actually runs."
        ),
        setup_notes="Seed the database and sign in as testuser.",
        test_file_name="reproduce.spec.js",
        test_code=_INTERCEPTING_TEST,
        expected_failure=(
            "The API error text never appears, because the catch block only "
            "logs to the console."
        ),
    )


def run_in_daytona(
    repo_url: str,
    plan: ReproductionPlan,
    setup_command: str | None = None,
    start_command: str | None = None,
    ref: str | None = None,
) -> ExecutionResult:
    """Return a canned execution result matching the attempt's plan."""
    if "page.route" not in plan.test_code:
        return ExecutionResult(
            exit_code=0,
            stdout=_ATTEMPT_ONE_STDOUT,
            stderr="",
            reproduced=False,
            reason="Test passed, so the reported behaviour did not occur.",
            artifacts=[],
            stage="test",
        )

    return ExecutionResult(
        exit_code=1,
        stdout=_ATTEMPT_TWO_STDOUT,
        stderr="",
        reproduced=True,
        reason="Assertion failed: the API error was never shown to the user",
        artifacts=["test-results/reproduce-failed/test-failed-1.png"],
        stage="test",
    )
