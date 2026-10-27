import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const backendRoot = path.resolve(frontendRoot, '../backend');
const python = path.join(backendRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const localBypass = [...new Set([...(process.env.NO_PROXY ?? '').split(','), ...(process.env.no_proxy ?? '').split(','),
  '127.0.0.1', 'localhost', '::1'].map((value) => value.trim()).filter(Boolean))].join(',');
process.env.NO_PROXY = localBypass;
process.env.no_proxy = localBypass;

// Explicit controlled model + fresh SQLite. This suite never invokes a model vendor or MySQL.
export default defineConfig({
  testDir: './e2e', testMatch: '**/agent-tasks.spec.ts', outputDir: '../output/playwright-agent',
  fullyParallel: false, workers: 1, retries: 0, timeout: 40000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5176', viewport: { width: 1440, height: 1000 },
    channel: process.env.HOMEMIND_BROWSER_CHANNEL || undefined, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: `"${python}" ../scripts/serve_agent_e2e.py --controlled-sqlite`, cwd: backendRoot,
      url: 'http://127.0.0.1:18110/health', reuseExistingServer: false, timeout: 30000,
      env: { HOMEMIND_ENVIRONMENT: 'test' } },
    { command: 'npm run dev -- --port 5176', cwd: frontendRoot, url: 'http://127.0.0.1:5176',
      env: { HOMEMIND_API_PROXY_TARGET: 'http://127.0.0.1:18110' }, reuseExistingServer: false, timeout: 30000 },
  ],
});
