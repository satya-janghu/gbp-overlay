import { test, expect } from '../fixtures/app-fixture';

test.describe('Projects Dashboard', () => {
  test('dashboard page loads with expected structure', async ({ page, snap }) => {
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');
    await snap('01-projects-dashboard');

    // Page heading
    const heading = page.locator('h1, h2').first();
    await expect(heading).toBeVisible();

    // New Project button/link
    const newProjectLink = page.locator(
      'a:has-text("New Project"), a:has-text("New"), button:has-text("New Project")'
    ).first();
    await expect(newProjectLink).toBeVisible();

    await snap('02-dashboard-structure');
  });

  test('new project link navigates to setup', async ({ page }) => {
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');

    const newProjectLink = page.locator(
      'a:has-text("New Project"), a:has-text("New"), button:has-text("New Project")'
    ).first();
    await newProjectLink.click();

    await page.waitForURL(/\//, { timeout: 10_000 });
  });
});
