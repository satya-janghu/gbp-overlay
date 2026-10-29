import { Page, TestInfo } from '@playwright/test';

export interface ApiLogEntry {
  method: string;
  url: string;
  status: number;
  duration: number;
  size: number | null;
}

export function setupApiLogger(page: Page): ApiLogEntry[] {
  const log: ApiLogEntry[] = [];
  const timings = new Map<string, number>();

  page.on('request', (request) => {
    if (request.url().includes('/api/')) {
      timings.set(request.url() + request.method(), Date.now());
    }
  });

  page.on('response', (response) => {
    const url = response.url();
    if (!url.includes('/api/')) return;

    const key = url + response.request().method();
    const startTime = timings.get(key);
    const duration = startTime ? Date.now() - startTime : 0;
    timings.delete(key);

    const contentLength = response.headers()['content-length'];
    log.push({
      method: response.request().method(),
      url: url.replace(/https?:\/\/[^/]+/, ''),
      status: response.status(),
      duration,
      size: contentLength ? parseInt(contentLength, 10) : null,
    });
  });

  return log;
}

export function formatApiLog(log: ApiLogEntry[]): string {
  if (log.length === 0) return 'No API calls recorded.';

  const lines = log.map(
    (entry) =>
      `${entry.method} ${entry.url} → ${entry.status} (${entry.duration}ms${entry.size ? `, ${entry.size}B` : ''})`
  );
  return lines.join('\n');
}
