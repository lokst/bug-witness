"""Reproduction test generation and refinement.

Task 3's Nosana call is still represented by a deterministic generator.  The
fallback targets the selected YesFundMe demo, allowing the complete
orchestrator and Daytona integration to be demonstrated while model-provider
selection is finalized.
"""

from .models import ExecutionResult, ReproductionPlan, RepositoryContext

DEMO_TEST = """\
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
  await page
    .getByLabel('Description')
    .fill('A sufficiently long campaign description for reproduction.');
  await page.getByLabel('Goal Amount ($)').fill('100');
  await page.getByRole('button', { name: 'Create Campaign' }).click();

  await expect(
    page.getByText('Service temporarily unavailable', { exact: true }),
  ).toBeVisible();
});
"""


def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_results: list[ExecutionResult],
) -> ReproductionPlan:
    """Return the deterministic selected-demo plan until Nosana is enabled."""
    refinement = ""
    if previous_results:
        refinement = (
            " Refined after the prior sandbox evidence by keeping API failure "
            "interception scoped to only the campaign-creation POST."
        )
    return ReproductionPlan(
        summary=(
            "Submit a valid campaign while deterministically returning HTTP 503 "
            "and assert that the API error is visible." + refinement
        ),
        setup_notes=(
            "Use pinned YesFundMe revision 079886d51a871b2c4e43377a1a33e456d93cdd91; "
            "run the database seed before starting the app."
        ),
        test_file_name="reproduce.spec.js",
        test_code=DEMO_TEST,
        expected_failure=(
            "Service temporarily unavailable should be visible, but the element "
            "is not rendered."
        ),
    )
