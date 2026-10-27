import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { register } from './helpers';

const outputDirectory = path.resolve(process.cwd(), '../output');
test.beforeEach(async ({ page, request }) => { await register(request, page); });

test('网页通过真实代理确认 HomeMind API 在线', async ({ page, request }) => {
  const response = await request.get('/api/health');
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({
    status: 'ok', service: 'homemind-api', version: '0.4.0', stage: 'M4',
  });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('后端已连接', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('家庭概览');
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
  await expect(page.getByRole('button', { name: /重新检查/ })).toBeEnabled();
  expect(errors).toEqual([]);
  await mkdir(outputDirectory, { recursive: true });
  await page.screenshot({ path: path.join(outputDirectory, 'product-b-regression-desktop.png'), fullPage: true });
  await page.screenshot({ path: path.join(outputDirectory, 'product-b-regression-desktop-overview.png') });
});

test('浏览器离线后显示失败，恢复网络并显式重试可连接', async ({ page, context }) => {
  await page.goto('/');
  await expect(page.getByText('后端已连接', { exact: true })).toBeVisible();
  await context.setOffline(true);
  await page.getByRole('button', { name: /重新检查/ }).click();
  await expect(page.getByText('后端暂未连接，请确认后端服务已启动。', { exact: true })).toBeVisible();
  await context.setOffline(false);
  await page.getByRole('button', { name: /重新检查/ }).click();
  await expect(page.getByText('后端已连接', { exact: true })).toBeVisible();
});

test('其他服务返回 200 也不能显示 HomeMind 在线', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({
    json: { status: 'ok', service: 'another-api', version: '1', stage: 'unknown' },
  }));
  await page.goto('/');
  await expect(page.getByText('后端返回了无法识别的服务信息。', { exact: true })).toBeVisible();
  await expect(page.getByText('后端已连接', { exact: true })).toHaveCount(0);
});

test('390px 手机视口可操作且没有横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByText('后端已连接', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /重新检查/ }).click();
  await expect(page.getByText('后端已连接', { exact: true })).toBeVisible();
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
  const geometry = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(geometry.page).toBeLessThanOrEqual(geometry.viewport);
  await mkdir(outputDirectory, { recursive: true });
  await page.screenshot({ path: path.join(outputDirectory, 'product-b-regression-mobile.png'), fullPage: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(outputDirectory, 'product-b-regression-mobile-overview.png') });
});
