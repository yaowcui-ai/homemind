import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const testPassword = 'HomeMind_browser_test_12345';
export function username() { return `e2e_${Date.now().toString(36)}_${crypto.randomUUID().slice(0, 8)}`; }
export async function write(request: APIRequestContext, method: string, path: string, data?: unknown, extraHeaders: Record<string, string> = {}) {
  const bootstrap = await request.get('/api/auth/session');
  expect(bootstrap.ok()).toBeTruthy();
  const session = await bootstrap.json();
  return request.fetch(`/api${path}`, { method,
    headers: { Origin: 'http://127.0.0.1:5174', 'X-CSRF-Token': session.csrf_token, ...extraHeaders },
    ...(data === undefined ? {} : { data }),
  });
}

export async function register(request: APIRequestContext, page?: Page) {
  const name = username();
  const response = await write(request, 'POST', '/auth/register', { username: name, password: testPassword });
  expect(response.status()).toBe(200);
  const session = await response.json();
  expect(session.user.username).toBe(name);
  if (page) await page.context().addCookies((await request.storageState()).cookies);
  return session;
}

export async function choose(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.locator('.ant-select-dropdown:visible').getByText(option, { exact: true }).click();
  await page.keyboard.press('Escape');
}
