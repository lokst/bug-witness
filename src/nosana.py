"""Reproduction test generation and refinement.

Task 3's Nosana call is still represented by a deterministic generator.  The
fallback targets the selected YesFundMe demo, allowing the complete
orchestrator and Daytona integration to be demonstrated while model-provider
selection is finalized.
"""

from .models import AttemptEvidence, ReproductionPlan, RepositoryContext

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

REFINED_DEMO_TEST = """\
const { test, expect } = require('@playwright/test');

test('shows the campaign API error using a request-scoped response', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username or Email').fill('testuser');
  await page.getByLabel('Password').fill('password123');
  await Promise.all([
    page.waitForURL(/\\/dashboard$/),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);

  await page.goto('/campaigns/new');
  await page.getByLabel('Campaign Title').fill('Playwright campaign');
  await page.getByLabel('Description').fill('A sufficiently long campaign description for reproduction.');
  await page.getByLabel('Goal Amount ($)').fill('100');

  const failedRequest = page.waitForResponse(
    response => response.url().includes('/api/campaigns') &&
      response.request().method() === 'POST' && response.status() === 503,
  );
  await page.route('**/api/campaigns', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'Service temporarily unavailable' }),
  }), { times: 1 });
  await page.getByRole('button', { name: 'Create Campaign' }).click();
  await failedRequest;

  await expect(page.getByText('Service temporarily unavailable', { exact: true })).toBeVisible();
});
"""


def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_attempts: list[AttemptEvidence],
) -> ReproductionPlan:
    """Return a deterministic evidence-aware plan until Nosana is enabled."""
    refinement = ""
    test_code = DEMO_TEST
    if previous_attempts:
        previous = previous_attempts[-1]
        refinement = (
            " Refined from the prior generated test and sandbox evidence "
            f"({previous.result.reason}); wait for login navigation and the failed "
            "campaign response, and intercept exactly one request."
        )
        test_code = REFINED_DEMO_TEST
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
        test_code=test_code,
        expected_failure=(
            "Service temporarily unavailable should be visible, but the element "
            "is not rendered."
        ),
    )
