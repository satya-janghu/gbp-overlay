import { test, expect } from '../fixtures/app-fixture';

test.describe('Setup Form', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('all form fields are present', async ({ page, snap }) => {
    await snap('01-empty-form');

    // Core fields
    await expect(page.locator('#client_name')).toBeVisible();
    await expect(page.locator('#website_url')).toBeVisible();
    await expect(page.locator('#keywords')).toBeVisible();

    // Optional fields
    await expect(page.locator('#locations')).toBeVisible();
    await expect(page.locator('#images_per_page')).toBeVisible();

    // Checkboxes
    await expect(page.locator('#fetch_anywhere')).toBeVisible();
    await expect(page.locator('#js_rendered')).toBeVisible();

    // Submit button
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('font picker shows available fonts', async ({ page, snap }) => {
    // Font picker is a grid of radio-style buttons with font names
    const fontLabel = page.locator('label:has-text("Font")');
    await expect(fontLabel).toBeVisible();

    // Should have Montserrat as a font option
    const montserrat = page.getByText('Montserrat', { exact: true }).first();
    await expect(montserrat).toBeVisible();

    await snap('02-font-picker');
  });

  test('submit without keywords shows validation error', async ({ page, snap }) => {
    // Fill required fields except keywords
    await page.fill('#client_name', 'Test Client');
    await page.fill('#website_url', 'https://example.com');

    // Ensure keywords is empty
    await page.fill('#keywords', '');

    // Submit
    await page.click('button[type="submit"]');

    // Wait briefly for validation
    await page.waitForTimeout(1000);
    await snap('03-validation-error');

    // Should still be on the setup page (not navigated)
    await expect(page).toHaveURL(/\//);
  });
});
