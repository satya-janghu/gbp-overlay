import { test, expect } from '../fixtures/app-fixture';
import { validateZipBuffer } from '../helpers/zip-validator';

test.describe('Download Regression', () => {
  test('download ZIP from a completed project', async ({ page, snap }) => {
    // Navigate to the app first to establish a session cookie
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');
    await snap('00-projects-page');

    // Use page.request (shares browser cookie jar) instead of standalone request fixture
    const response = await page.request.get('/api/projects');
    expect(response.status()).toBe(200);

    const data = await response.json();
    const completedProject = data.completed?.find(
      (p: any) => p.status === 'complete' || p.status === 'completed'
    ) ?? null;

    if (!completedProject) {
      test.skip(true, 'No completed projects found — skipping download regression test');
      return;
    }

    const projectId = completedProject.id;
    console.log(`Testing download for completed project ${projectId}: ${completedProject.client_name}`);

    // Navigate to the project page
    await page.goto(`/project/${projectId}/progress`);
    await page.waitForLoadState('networkidle');
    await snap('01-completed-project');

    // Direct API download using page.request (shares session cookies)
    const downloadResponse = await page.request.get(`/api/projects/${projectId}/download`);
    console.log(`Download API status: ${downloadResponse.status()}`);
    console.log(`Content-Type: ${downloadResponse.headers()['content-type']}`);
    console.log(`Content-Length: ${downloadResponse.headers()['content-length']}`);

    if (downloadResponse.status() === 200) {
      const body = await downloadResponse.body();
      const zipResult = validateZipBuffer(body);

      console.log(`ZIP size: ${zipResult.sizeBytes} bytes`);
      console.log(`ZIP files: ${zipResult.fileCount}`);
      console.log(`JPG count: ${zipResult.jpgCount}`);
      console.log(`Has manifest: ${zipResult.hasManifest}`);
      console.log(`Valid: ${zipResult.valid}`);

      if (zipResult.errors.length > 0) {
        console.log(`Errors: ${zipResult.errors.join(', ')}`);
      }
      if (zipResult.filenames.length <= 20) {
        console.log(`Files: ${zipResult.filenames.join(', ')}`);
      }

      // Hard assertion: ZIP must be valid
      expect(zipResult.valid, `ZIP invalid: ${zipResult.errors.join(', ')}`).toBe(true);
      expect(zipResult.jpgCount).toBeGreaterThan(0);
    } else {
      const bodyText = await downloadResponse.text().catch(() => 'Could not read body');
      console.log(`Download failed: ${bodyText}`);

      // Hard fail: download endpoint returned non-200
      expect(downloadResponse.status(), 'Download endpoint should return 200').toBe(200);
    }

    await snap('02-download-result');
  });
});
