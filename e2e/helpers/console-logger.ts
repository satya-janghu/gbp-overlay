import { Page } from '@playwright/test';

export interface ConsoleEntry {
  type: string;
  text: string;
  location: string;
}

export function setupConsoleLogger(page: Page): ConsoleEntry[] {
  const entries: ConsoleEntry[] = [];

  page.on('console', (msg) => {
    const type = msg.type();
    if (type === 'error' || type === 'warning') {
      entries.push({
        type,
        text: msg.text(),
        location: msg.location()
          ? `${msg.location().url}:${msg.location().lineNumber}`
          : 'unknown',
      });
    }
  });

  return entries;
}

export function formatConsoleLog(entries: ConsoleEntry[]): string {
  if (entries.length === 0) return 'No console errors or warnings.';

  return entries
    .map((e) => `[${e.type.toUpperCase()}] ${e.text} (${e.location})`)
    .join('\n');
}
