const { test, expect } = require('@playwright/test');

test('shows the API error when campaign creation fails', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username or Email').fill('testuser');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  // Make the server-side failure deterministic without depending on an outage.
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

  // Expected product behavior: communicate the API failure to the user.
  // Current behavior: CreateCampaign catches and only console.logs the error.
  await expect(
    page.getByText('Service temporarily unavailable', { exact: true }),
  ).toBeVisible();
});
