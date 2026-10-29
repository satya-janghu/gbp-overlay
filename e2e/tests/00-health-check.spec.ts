import { test, expect } from '@playwright/test';

test.describe('Health Check', () => {
  test('GET /health returns 200 with status key', async ({ request }) => {
    const response = await request.get('/health');

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('status');
    expect(body.status).toBe('ok');
  });
});
