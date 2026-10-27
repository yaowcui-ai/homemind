import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { choose, register, write } from './helpers';
import type { TaskDetail } from '../src/api/tasks.types';
import type { Snapshot } from '../src/api/simulation.types';

test.beforeEach(async ({ page, request }) => { await register(request, page); });
async function navigate(page: Page, view = '规则任务') {
  await page.getByRole('button', { name: view, exact: true }).filter({ visible: true }).first().click();
}
async function create(page: Page): Promise<TaskDetail> {
  const response = page.waitForResponse((r) => r.url().endsWith('/api/tasks') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '执行规则任务', exact: true }).click();
  const actual = await response; expect(actual.status()).toBe(200);
  const detail: TaskDetail = await actual.json();
  await expect(page.getByRole('region', { name: '任务详情' })).toBeVisible();
  return detail;
}

test('离家任务实际执行并保留历史，刷新不会重发任务', async ({ page, request }) => {
  const data: Snapshot = await (await request.get('/api/simulation')).json();
  const lamp = data.entities.find((e) => e.type === 'light' && e.room_id === data.rooms[0].id)!;
  expect((await write(request, 'POST', `/simulation/controls/${lamp.id}`, { action: 'set_light', parameters: { power: true } })).ok()).toBeTruthy();
  await page.goto('/'); await navigate(page); await choose(page, '场景模板', '离家模式');
  const task = await create(page);
  expect(task.status).toBe('succeeded');
  await expect(page.getByRole('region', { name: '任务详情' }).getByText('全部条件已核验', { exact: true })).toBeVisible();
  const after: Snapshot = await (await request.get('/api/simulation')).json();
  expect(after.entities.find((e) => e.id === lamp.id)!.state.power).toBe(false);
  await page.getByRole('region', { name: '任务详情' }).screenshot({ path: path.resolve('../output/m3-task-result.png') });
  await page.reload(); await navigate(page);
  await page.getByRole('region', { name: '任务列表' }).getByRole('button', { name: /离家模式/ }).first().click();
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('回家方案区分动作和未来目标，按时核验不重发动作', async ({ page, request }) => {
  await page.goto('/'); await navigate(page);
  await page.getByLabel('目标温度（℃）', { exact: true }).fill('28');
  await page.getByLabel('准备时间（仿真分钟）', { exact: true }).fill('1');
  const task = await create(page);
  expect(task.status).toBe('waiting_verification');
  await expect(page.getByRole('region', { name: '任务详情' }).getByText('等待目标核验', { exact: true })).toBeVisible();
  await navigate(page, '家庭概览');
  await page.getByRole('button', { name: '推进 1 分钟', exact: true }).click();
  await expect(page.getByText('已推进 1 分钟', { exact: true })).toBeVisible();
  await navigate(page);
  await page.getByRole('region', { name: '任务列表' }).getByRole('button', { name: /回家准备/ }).first().click();
  await page.getByRole('button', { name: '核验目标', exact: true }).click();
  await expect(page.getByRole('region', { name: '任务详情' }).getByText('全部条件已核验', { exact: true })).toBeVisible();
  const verified: TaskDetail = await (await request.get(`/api/tasks/${task.id}`)).json();
  expect(verified.actions.map((a) => a.id)).toEqual(task.actions.map((a) => a.id));
  expect(verified.verification.checked_at_minutes).toBe(1);
});

test('睡眠方案遇到未知窗户保留部分完成，不伪造制冷成功', async ({ page, request }) => {
  const data: Snapshot = await (await request.get('/api/simulation')).json();
  const window = data.entities.find((e) => e.type === 'window' && e.room_id === data.rooms[0].id)!;
  expect((await write(request, 'POST', '/simulation/events', { entity_id: window.id, known: false })).ok()).toBeTruthy();
  await page.goto('/'); await navigate(page); await choose(page, '场景模板', '睡眠模式');
  const task = await create(page);
  expect(task.status).toBe('partial');
  await expect(page.getByRole('region', { name: '任务详情' }).getByText('部分完成', { exact: true })).toBeVisible();
  expect(task.verification.conditions.some((c) => c.outcome === 'unknown')).toBe(true);
});

test('偏好保存后新任务使用新默认值，390px任务表单无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/'); await navigate(page, '偏好设置');
  await page.getByLabel('回家目标温度（℃）', { exact: true }).fill('25');
  await page.getByRole('button', { name: '保存偏好', exact: true }).click();
  await expect(page.getByText('偏好已保存，新任务会使用这些设置。', { exact: true })).toBeVisible();
  await navigate(page);
  await expect(page.getByLabel('目标温度（℃）', { exact: true })).toHaveValue('25');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole('region', { name: '规则任务表单' }).screenshot({ path: path.resolve('../output/m3-task-mobile.png') });
});

test('已提交但响应丢失后，切换概览再重试相同任务仍复用幂等键', async ({ page, request }) => {
  const keys: string[] = [];
  let first = true;
  await page.route('**/api/tasks', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    keys.push(route.request().headers()['idempotency-key']);
    if (first) {
      first = false;
      const committed = await route.fetch(); expect(committed.status()).toBe(200);
      await route.abort('failed');
    } else await route.continue();
  });
  await page.goto('/'); await navigate(page); await choose(page, '场景模板', '离家模式');
  await page.getByRole('button', { name: '执行规则任务', exact: true }).click();
  await expect(page.getByText(/无法连接服务/)).toBeVisible();
  await navigate(page, '家庭概览'); await navigate(page);
  await choose(page, '场景模板', '离家模式'); await create(page);
  expect(keys.length).toBe(2); expect(keys[0]).toBe(keys[1]);
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('同账号窗口重新获得焦点后，未知提交仍保留原幂等键', async ({ page, request }) => {
  const keys: string[] = []; let first = true;
  await page.route('**/api/tasks', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    keys.push(route.request().headers()['idempotency-key']);
    if (first) {
      first = false; expect((await route.fetch()).status()).toBe(200); await route.abort('failed');
    } else await route.continue();
  });
  await page.goto('/'); await navigate(page); await choose(page, '场景模板', '离家模式');
  await page.getByRole('button', { name: '执行规则任务', exact: true }).click();
  await expect(page.getByText(/无法连接服务/)).toBeVisible();
  const refreshed = page.waitForResponse((r) => r.url().endsWith('/api/auth/session'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await refreshed;
  await navigate(page); await choose(page, '场景模板', '离家模式'); await create(page);
  expect(keys[0]).toBe(keys[1]);
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});
