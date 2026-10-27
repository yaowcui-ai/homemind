import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const backendRoot = path.resolve(frontendRoot, '../backend');
const python = path.join(backendRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

// Playwright's readiness checks honor proxy environment variables. Keep local
// tests on loopback without changing the user's shell or system proxy settings.
const localBypass = [...new Set([
  ...(process.env.NO_PROXY ?? '').split(','),
  ...(process.env.no_proxy ?? '').split(','),
  '127.0.0.1', 'localhost', '::1',
].map((value) => value.trim()).filter(Boolean))].join(',');
process.env.NO_PROXY = localBypass;
process.env.no_proxy = localBypass;

export default defineConfig({
  testDir: './e2e',
  outputDir: '../output/playwright',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    viewport: { width: 1440, height: 1000 },
    channel: process.env.HOMEMIND_BROWSER_CHANNEL || undefined,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" ../scripts/serve_e2e.py`,
      cwd: backendRoot,
      url: 'http://127.0.0.1:8100/health',
      env: { HOMEMIND_API_HOST: '127.0.0.1', HOMEMIND_API_PORT: '8100', HOMEMIND_ENVIRONMENT: 'test' },
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: 'npm run dev',
      cwd: frontendRoot,
      url: 'http://127.0.0.1:5174',
      env: { HOMEMIND_API_PROXY_TARGET: 'http://127.0.0.1:8100' },
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
