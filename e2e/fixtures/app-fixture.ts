import { test as base } from '@playwright/test';
import { ApiLogEntry, setupApiLogger, formatApiLog } from '../helpers/api-logger';
import { ConsoleEntry, setupConsoleLogger, formatConsoleLog } from '../helpers/console-logger';
import * as fs from 'fs';
import * as path from 'path';

interface AppFixtures {
  apiLog: ApiLogEntry[];
  consoleErrors: ConsoleEntry[];
  snap: (name: string) => Promise<void>;
}

export const test = base.extend<AppFixtures>({
  apiLog: async ({ page }, use) => {
    const log = setupApiLogger(page);
    await use(log);
    if (log.length > 0) {
      const info = test.info();
      await info.attach('api-log', {
        body: formatApiLog(log),
        contentType: 'text/plain',
      });
    }
  },

  consoleErrors: async ({ page }, use) => {
    const entries = setupConsoleLogger(page);
    await use(entries);
    if (entries.length > 0) {
      const info = test.info();
      await info.attach('console-errors', {
        body: formatConsoleLog(entries),
        contentType: 'text/plain',
      });
    }
  },

  snap: async ({ page }, use) => {
    const info = test.info();
    const snapFn = async (name: string) => {
      const testName = sanitizeFilename(info.title);
      const dir = path.join('screenshots', testName);
      fs.mkdirSync(dir, { recursive: true });

      const filePath = path.join(dir, `${name}.png`);
      await page.screenshot({ path: filePath, fullPage: true });

      await info.attach(name, {
        path: filePath,
        contentType: 'image/png',
      });
    };
    await use(snapFn);
  },
});

export { expect } from '@playwright/test';

function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 80);
}
