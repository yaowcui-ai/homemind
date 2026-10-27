import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { testPassword, username, write } from './helpers';

async function credentials(page: Page, name: string, registering: boolean) {
  if (registering) await page.getByRole('button', { name: /^注\s*册$/ }).click();
  await page.getByLabel('用户名', { exact: true }).fill(name);
  await page.getByLabel('密码', { exact: true }).fill(testPassword);
  await page.getByRole('button', { name: registering ? '注册并创建家庭' : '登录我的家庭' }).click();
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
}

test('未登录先显示账号入口，HttpOnly会话注册后才可读取家庭', async ({ page, request }) => {
  expect((await request.get('/api/simulation')).status()).toBe(401);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await expect(page.getByTestId('entity-count')).toHaveCount(0);
  await page.screenshot({ path: path.resolve('../output/figma-sync-login.png'), fullPage: true });
  await credentials(page, username(), true);
  const cookies = await page.context().cookies();
  expect(cookies.find((cookie) => cookie.name === 'homemind_session')?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain('homemind_session');
});

test('同一浏览器退出并切换账号不显示旧家庭，重新登录恢复原配置', async ({ page }) => {
  test.setTimeout(60000);
  const userA = username(), userB = username();
  await page.goto('/'); await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await credentials(page, userA, true);
  const before = await (await page.request.get('/api/simulation')).json();
  expect((await write(page.request, 'PATCH', `/simulation/rooms/${before.rooms[0].id}`, { name: '账号甲的房间' })).ok()).toBeTruthy();
  await page.getByRole('button', { name: '读取状态', exact: true }).click();
  await expect(page.getByRole('heading', { name: '账号甲的房间', exact: true })).toBeVisible();
  const lamp = page.getByRole('article', { name: '客厅主灯', exact: true });
  await lamp.getByRole('switch', { name: '客厅主灯目标开关' }).click();
  await lamp.getByRole('button', { name: '应用设置' }).click();
  await expect(lamp.getByText('已开启 · 60%', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  expect((await page.request.get('/api/simulation')).status()).toBe(401);
  await credentials(page, userB, true);
  await expect(page.getByRole('heading', { name: '账号甲的房间', exact: true })).toHaveCount(0);
  await expect(page.getByRole('article', { name: '客厅主灯', exact: true }).getByText('已关闭', { exact: true })).toBeVisible();
  const other = await (await page.request.get('/api/simulation')).json();
  expect(other.home_id).not.toBe(before.home_id);
  expect(other.entities.map((e: { id: string }) => e.id)).not.toContain(before.entities[0].id);
  expect((await write(page.request, 'PATCH', `/simulation/rooms/${before.rooms[0].id}`, { name: '不能越权' })).status()).toBe(404);
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await credentials(page, userA, false);
  await expect(page.getByRole('heading', { name: '账号甲的房间', exact: true })).toBeVisible();
  await expect(page.getByRole('article', { name: '客厅主灯', exact: true }).getByText('已开启 · 60%', { exact: true })).toBeVisible();
});

test('另一标签页切换账号后，本页同步身份并清理旧家庭', async ({ page }) => {
  test.setTimeout(60000);
  const userA = username(), userB = username();
  await page.goto('/'); await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await credentials(page, userA, true);
  const before = await (await page.request.get('/api/simulation')).json();
  expect((await write(page.request, 'PATCH', `/simulation/rooms/${before.rooms[0].id}`, { name: '旧标签页的私有房间' })).ok()).toBeTruthy();
  await page.getByRole('button', { name: '读取状态', exact: true }).click();
  await expect(page.getByRole('heading', { name: '旧标签页的私有房间' })).toBeVisible();
  const otherTab = await page.context().newPage();
  await otherTab.goto('/'); await expect(otherTab.getByTestId('entity-count')).toHaveText('12个');
  await otherTab.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(otherTab.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await credentials(otherTab, userB, true);
  await page.bringToFront();
  await expect(page.getByTitle(userB, { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '旧标签页的私有房间' })).toHaveCount(0);
  await page.getByRole('button', { name: '读取状态', exact: true }).click();
  await expect(page.getByRole('heading', { name: '客厅', exact: true })).toBeVisible();
  await otherTab.close();
});

test('同一匿名会话恢复焦点时保留未提交的登录输入', async ({ page }) => {
  await page.goto('/'); await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await page.getByLabel('用户名', { exact: true }).fill('draft_user');
  await page.getByLabel('密码', { exact: true }).fill(testPassword);
  const refreshed = page.waitForResponse((r) => r.url().endsWith('/api/auth/session'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await refreshed;
  await expect(page.getByLabel('用户名', { exact: true })).toBeVisible();
  await expect(page.getByLabel('用户名', { exact: true })).toHaveValue('draft_user');
  await expect(page.getByLabel('密码', { exact: true })).toHaveValue(testPassword);
});

test('会话核对期间编辑弹窗也被遮蔽，同账号确认后保留草稿', async ({ page }) => {
  await page.goto('/'); await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await credentials(page, username(), true);
  await page.getByRole('region', { name: '客厅房间', exact: true }).getByRole('button', { name: '房间设置' }).click();
  const dialog = page.getByRole('dialog', { name: '编辑房间', exact: true });
  await dialog.getByLabel('房间名称', { exact: true }).fill('会话内的私有房间草稿');
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/auth/session', async (route) => { await hold; await route.continue(); });
  const requested = page.waitForRequest((r) => r.url().endsWith('/api/auth/session'));
  const refreshed = page.waitForResponse((r) => r.url().endsWith('/api/auth/session'));
  try {
    await page.evaluate(() => window.dispatchEvent(new Event('focus'))); await requested;
    await expect(dialog).not.toBeVisible();
  } finally { release(); }
  await refreshed;
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('房间名称', { exact: true })).toHaveValue('会话内的私有房间草稿');
});
