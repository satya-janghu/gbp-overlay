import { test, expect } from '../fixtures/app-fixture';
import { TEST_PROJECT } from '../fixtures/test-data';
import { validateZipBuffer } from '../helpers/zip-validator';

test.describe('Full Flow: Setup -> Pipeline -> Review -> Generate -> Download', () => {
  test('complete end-to-end workflow', async ({ page, snap, apiLog, consoleErrors }) => {
    // --- Step A: Setup ---
    await test.step('A: Fill and submit setup form', async () => {
      await page.goto('/');
      await snap('01-setup-empty');

      await page.fill('#client_name', TEST_PROJECT.clientName);
      await page.fill('#website_url', TEST_PROJECT.websiteUrl);
      await page.fill('#keywords', TEST_PROJECT.keywords.join('\n'));

      await snap('02-setup-filled');

      await page.click('button[type="submit"]');

      await page.waitForURL(/\/project\/\d+\/review/, { timeout: 30_000 });
      await snap('03-navigated-to-review');
    });

    // Extract project ID from URL
    const url = page.url();
    const projectIdMatch = url.match(/\/project\/(\d+)\//);
    const projectId = projectIdMatch?.[1];
    expect(projectId).toBeTruthy();

    // --- Step B: Pipeline Processing ---
    await test.step('B: Wait for pipeline to complete', async () => {
      await snap('04-pipeline-start');

      let snapIndex = 0;
      const periodicSnap = setInterval(async () => {
        try {
          snapIndex++;
          await snap(`04-pipeline-progress-${String(snapIndex).padStart(2, '0')}`);
        } catch {
          // ignore
        }
      }, 30_000);

      try {
        await page.getByText('Review Images').waitFor({ timeout: 600_000 });
      } finally {
        clearInterval(periodicSnap);
      }

      await snap('05-pipeline-complete');
    });

    // --- Step C: Review Images ---
    await test.step('C: Verify review page content', async () => {
      await snap('06-review-overview');

      const images = page.locator('img');
      const imgCount = await images.count();
      console.log(`Found ${imgCount} images on review page`);

      await snap('07-review-details');
    });

    // --- Step D: Generate Overlays ---
    let generationSucceeded = false;
    await test.step('D: Start generation and wait for completion', async () => {
      const generateBtn = page.getByRole('button', { name: /generate/i });

      await expect(generateBtn).toBeVisible({ timeout: 10_000 });
      await snap('08-before-generate');

      await generateBtn.click();

      await snap('09-generation-start');

      let genSnapIndex = 0;
      const periodicGenSnap = setInterval(async () => {
        try {
          genSnapIndex++;
          await snap(`09-generation-progress-${String(genSnapIndex).padStart(2, '0')}`);
        } catch {
          // ignore
        }
      }, 15_000);

      try {
        // Wait for either: completion, or URL change to progress page, or error
        // The app navigates to /project/:id/progress after clicking Generate
        // Then shows "Complete!" when done
        const completeText = page.getByText('Complete!');
        const errorBanner = page.locator('text=Internal Server Error').or(page.locator('text=Error'));
        const downloadZipBtn = page.locator('button').filter({ hasText: 'Download ZIP' });

        // Poll for completion, error, or download button appearing
        const startTime = Date.now();
        const timeout = 600_000; // 10 minutes

        while (Date.now() - startTime < timeout) {
          if (await completeText.isVisible().catch(() => false)) {
            console.log('Generation completed successfully!');
            generationSucceeded = true;
            break;
          }
          if (await downloadZipBtn.isVisible().catch(() => false)) {
            console.log('Download ZIP button visible — generation complete');
            generationSucceeded = true;
            break;
          }
          if (await errorBanner.first().isVisible().catch(() => false)) {
            console.log('Error detected during generation');
            await snap('09-generation-error');
            break;
          }
          await page.waitForTimeout(3_000);
        }
      } finally {
        clearInterval(periodicGenSnap);
      }

      await snap('10-generation-result');
    });

    // --- Step E: Download ZIP ---
    await test.step('E: Download and validate ZIP', async () => {
      await page.waitForTimeout(2_000);
      await snap('10b-before-download');
      console.log(`Current URL: ${page.url()}`);

      // === Strategy 1: Direct API download (reliable) ===
      // Uses page.request which shares the browser's cookie jar (session auth)
      // This bypasses the fetch+blob+createObjectURL pattern that breaks Playwright interception
      const apiResponse = await page.request.get(
        `/api/projects/${projectId}/download`
      );
      console.log(`API download: status=${apiResponse.status()}`);
      console.log(`Content-Type: ${apiResponse.headers()['content-type']}`);
      console.log(`Content-Length: ${apiResponse.headers()['content-length']}`);

      if (apiResponse.status() === 200) {
        const body = await apiResponse.body();
        const zipResult = validateZipBuffer(body);
        console.log(`ZIP: valid=${zipResult.valid}, files=${zipResult.fileCount}, jpgs=${zipResult.jpgCount}, manifest=${zipResult.hasManifest}`);
        if (zipResult.filenames.length <= 30) {
          console.log(`Files: ${zipResult.filenames.join(', ')}`);
        }
        if (zipResult.errors.length > 0) {
          console.log(`ZIP errors: ${zipResult.errors.join(', ')}`);
        }
        // Hard assertion: if API returns 200, the ZIP must be valid
        expect(zipResult.valid, `ZIP invalid: ${zipResult.errors.join(', ')}`).toBe(true);
        expect(zipResult.jpgCount).toBeGreaterThan(0);
      } else {
        const bodyText = await apiResponse.text().catch(() => 'unreadable');
        console.log(`API download body: ${bodyText.substring(0, 500)}`);
        // Hard fail: download endpoint returned non-200
        expect(apiResponse.status(), 'Download endpoint should return 200').toBe(200);
      }

      // === Strategy 2: UI button click (verify UX works) ===
      const downloadBtn = page.locator('button').filter({ hasText: 'Download' })
        .or(page.locator('a').filter({ hasText: 'Download' }));
      const btnVisible = await downloadBtn.first().isVisible().catch(() => false);
      console.log(`Download button visible in UI: ${btnVisible}`);
      expect.soft(btnVisible, 'Download button should be visible on completion page').toBe(true);

      if (btnVisible) {
        await downloadBtn.first().click();
        await page.waitForTimeout(3_000); // give fetch+blob time
        await snap('11-after-download-click');
      }

      await snap('12-download-complete');
    });

    // --- Step F: Projects Dashboard ---
    await test.step('F: Check projects dashboard', async () => {
      await page.goto('/projects');
      await page.waitForLoadState('networkidle');
      await snap('13-projects-dashboard');

      const projectText = page.getByText(TEST_PROJECT.clientName);
      await expect(projectText.first()).toBeVisible({ timeout: 10_000 });
    });

    // --- Log summary ---
    console.log(`\n--- API Log (${apiLog.length} calls) ---`);
    for (const entry of apiLog.slice(-20)) {
      console.log(`  ${entry.method} ${entry.url} -> ${entry.status} (${entry.duration}ms)`);
    }

    if (consoleErrors.length > 0) {
      console.log(`\n--- Console Errors (${consoleErrors.length}) ---`);
      for (const entry of consoleErrors.slice(0, 10)) {
        console.log(`  [${entry.type}] ${entry.text}`);
      }
    }
  });
});
