import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import type { Snapshot } from '../src/api/simulation.types';
import { register, write } from './helpers';

async function snapshot(request: APIRequestContext): Promise<Snapshot> {
  const response = await request.get('/api/simulation');
  expect(response.status()).toBe(200);
  return response.json();
}

async function post(request: APIRequestContext, path: string, data: unknown) {
  const response = await write(request, 'POST', `/simulation${path}`, data);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function overview(page: Page) {
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '家庭概览' }).click();
}

test.beforeEach(async ({ request, page }) => { await register(request, page); await post(request, '/reset', {}); });

test.afterEach(async ({ request }) => {
  // Reset intentionally preserves configuration. Clean only this suite's additions,
  // including when an assertion fails, so later tests keep their own preconditions.
  let data = await snapshot(request);
  for (const entity of data.entities.filter((e) => ['阅读灯', '书桌灯', '测试温度计'].includes(e.name))) {
    expect((await write(request, 'DELETE', `/simulation/entities/${entity.id}`)).ok()).toBeTruthy();
  }
  data = await snapshot(request);
  for (const room of data.rooms.filter((r) => ['书房', '测试室', 'W'.repeat(40)].includes(r.name))) {
    expect((await write(request, 'DELETE', `/simulation/rooms/${room.id}`)).ok()).toBeTruthy();
  }
  const renamed = data.rooms.find((r) => r.name === '起居室');
  if (renamed) expect((await write(request, 'PATCH', `/simulation/rooms/${renamed.id}`, { name: '客厅' })).ok()).toBeTruthy();
});

test('灯、空调、窗帘控制读回与温度能耗变化，传感器走模拟事件', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
  const initial = await snapshot(request);
  const living = initial.rooms.find((r) => r.name === '客厅')!;
  const lamp = page.getByRole('article', { name: '客厅主灯', exact: true });
  await lamp.getByRole('switch', { name: '客厅主灯目标开关' }).click();
  await lamp.getByRole('spinbutton', { name: '客厅主灯亮度' }).fill('70');
  await lamp.getByRole('button', { name: '应用设置' }).click();
  await expect(lamp.getByText('已开启 · 70%', { exact: true })).toBeVisible();

  const climate = page.getByRole('article', { name: '客厅空调', exact: true });
  await climate.getByRole('combobox', { name: '客厅空调模式' }).click();
  await page.locator('.ant-select-dropdown:visible').getByText('制冷', { exact: true }).click();
  await climate.getByRole('spinbutton', { name: '客厅空调目标温度' }).fill('24');
  await climate.getByRole('button', { name: '应用设置' }).click();
  await expect(climate.getByText('制冷 · 目标 24℃', { exact: true })).toBeVisible();

  const cover = page.getByRole('article', { name: '客厅电动窗帘', exact: true });
  await cover.getByRole('spinbutton', { name: '客厅电动窗帘开度' }).fill('0');
  await cover.getByRole('button', { name: '应用设置' }).click();
  await expect(cover.getByText('开度 0%', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '推进 20 分钟', exact: true }).click();
  await expect(page.getByText('已推进 20 分钟', { exact: true })).toBeVisible();
  const after = await snapshot(request);
  expect(after.simulated_minutes).toBe(20);
  expect(after.rooms.find((r) => r.id === living.id)!.temperature_c).toBeLessThan(living.temperature_c!);
  expect(after.energy_wh).toBeGreaterThan(0);

  const occupancy = page.getByRole('article', { name: '客厅有人传感器', exact: true });
  await expect(occupancy.getByRole('button', { name: '应用设置' })).toHaveCount(0);
  await occupancy.getByRole('button', { name: '模拟有人' }).click();
  await expect(occupancy.getByText('有人', { exact: true })).toBeVisible();
  await page.getByRole('article', { name: '客厅窗户传感器', exact: true }).getByRole('button', { name: '模拟开窗' }).click();
  await expect(page.getByRole('article', { name: '客厅窗户传感器', exact: true }).getByText('窗户打开', { exact: true })).toBeVisible();
  const events = await snapshot(request);
  expect(events.rooms.find((r) => r.id === living.id)).toMatchObject({ occupied: true, window_open: true });
});

test('配置房间、增灯、改名迁移、归档，重置保留用户配置', async ({ page, request }) => {
  test.setTimeout(60000);
  await page.goto('/');
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '家庭配置' }).click();
  await page.getByRole('button', { name: '新增房间', exact: true }).click();
  const roomDialog = page.getByRole('dialog', { name: '新增房间' });
  await roomDialog.getByLabel('房间名称').fill('书房');
  await roomDialog.getByRole('button', { name: '保存房间' }).click();
  await expect(roomDialog).not.toBeVisible();
  const study = page.getByRole('region', { name: '书房配置', exact: true });
  await study.getByRole('button', { name: '新增实体' }).click();
  let entityDialog = page.getByRole('dialog', { name: '新增实体' });
  await entityDialog.getByLabel('实体名称').fill('阅读灯');
  await entityDialog.getByRole('button', { name: '保存实体' }).click();
  await expect(entityDialog).not.toBeVisible();
  await expect(page.getByTestId('entity-count')).toHaveText('13个');
  const created = (await snapshot(request)).entities.find((e) => e.name === '阅读灯')!;

  await study.locator('[aria-label="阅读灯"]').getByRole('button', { name: '编辑实体' }).click();
  entityDialog = page.getByRole('dialog', { name: '编辑实体' });
  await entityDialog.getByLabel('实体名称').fill('书桌灯');
  await entityDialog.getByLabel('所属房间').click();
  await page.locator('.ant-select-dropdown:visible').getByText('客厅', { exact: true }).click();
  await entityDialog.getByRole('button', { name: '保存实体' }).click();
  await expect(entityDialog).not.toBeVisible();
  const moved = await snapshot(request);
  expect(moved.entities.find((e) => e.name === '书桌灯')!.id).toBe(created.id);
  const living = page.getByRole('region', { name: '客厅配置', exact: true });
  await living.getByRole('button', { name: '编辑房间' }).click();
  const editRoom = page.getByRole('dialog', { name: '编辑房间' });
  await editRoom.getByLabel('房间名称').fill('起居室');
  await editRoom.getByRole('button', { name: '保存房间' }).click();
  await expect(editRoom).not.toBeVisible();
  await study.getByRole('button', { name: '移除房间' }).click();
  await page.getByRole('button', { name: '确认移除', exact: true }).click();
  await expect(study).toHaveCount(0);
  await page.getByRole('region', { name: '起居室配置', exact: true }).locator('[aria-label="书桌灯"]').getByRole('button', { name: '移除实体' }).click();
  await page.getByRole('button', { name: '确认移除', exact: true }).click();
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
  await page.getByRole('button', { name: '重置运行', exact: true }).click();
  await page.getByRole('button', { name: '确认重置', exact: true }).click();
  await expect(page.getByText('运行状态已重置，用户配置保持不变', { exact: true })).toBeVisible();
  const reset = await snapshot(request);
  expect(reset.entities.some((e) => e.id === created.id)).toBe(false);
  expect(reset.rooms.find((r) => r.name === '起居室')).toBeDefined();
  expect(reset.world_id).not.toBe(moved.world_id);
  expect(reset.config_revision).toBeGreaterThan(moved.config_revision);
  // Restore the default room label for subsequent checks; preserve archived history.
  const renamed = reset.rooms.find((r) => r.name === '起居室')!;
  expect((await write(request, 'PATCH', `/simulation/rooms/${renamed.id}`, { name: '客厅' })).ok()).toBeTruthy();
});

test('主传感器删除后房间显示未知，不用其他信号冒充', async ({ page, request }) => {
  let data: Snapshot = await post(request, '/rooms', { name: '测试室' });
  const room = data.rooms.find((r) => r.name === '测试室')!;
  data = await post(request, '/entities', { room_id: room.id, name: '测试温度计', type: 'temperature' });
  const sensor = data.entities.find((e) => e.name === '测试温度计')!;
  expect((await write(request, 'PATCH', `/simulation/rooms/${room.id}`, { primary_temperature_entity_id: sensor.id })).ok()).toBeTruthy();
  await page.goto('/');
  await expect(page.getByRole('region', { name: '测试室房间', exact: true }).getByText(/室温 27.0℃/)).toBeVisible();
  await page.getByRole('article', { name: '测试温度计', exact: true }).getByRole('button', { name: '编辑实体' }).click();
  const editor = page.getByRole('dialog', { name: '编辑实体' });
  await editor.getByRole('button', { name: /取\s*消/ }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '家庭配置' }).click();
  await page.getByRole('region', { name: '测试室配置', exact: true }).getByRole('button', { name: '移除实体' }).click();
  await page.getByRole('button', { name: '确认移除', exact: true }).click();
  await expect(page.getByTestId('entity-count')).toHaveText('12个');
  await overview(page);
  await expect(page.getByRole('region', { name: '测试室房间', exact: true }).getByText(/室温 未知/)).toBeVisible();
  expect((await snapshot(request)).rooms.find((r) => r.id === room.id)!.primary_temperature_entity_id).toBeNull();
  expect((await write(request, 'DELETE', `/simulation/rooms/${room.id}`)).ok()).toBeTruthy();
});

test('离线、响应丢失、延迟动作都有真实读回和明确结果', async ({ page, request }) => {
  test.setTimeout(60000);
  await page.goto('/');
  const lamp = page.getByRole('article', { name: '客厅主灯', exact: true });
  await lamp.getByRole('button', { name: '故障设置', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: '客厅主灯 · 故障设置' });
  await drawer.getByRole('combobox', { name: '故障类型' }).click();
  await page.locator('.ant-select-dropdown:visible').getByText('设备离线', { exact: true }).click();
  await drawer.getByRole('button', { name: '应用故障规则' }).click();
  await expect(drawer).not.toBeVisible();
  await expect(lamp.getByText('离线', { exact: true })).toBeVisible();
  await expect(lamp.getByRole('button', { name: '应用设置' })).toBeDisabled();
  const data = await snapshot(request);
  const light = data.entities.find((e) => e.name === '客厅主灯')!;
  await post(request, `/faults/${light.id}`, { mode: 'response_lost' });
  await page.getByRole('button', { name: '读取状态', exact: true }).click();
  await expect(lamp.getByRole('button', { name: '应用设置' })).toBeEnabled();
  await lamp.getByRole('switch', { name: '客厅主灯目标开关' }).click();
  const lost = page.waitForResponse((r) => r.url().includes(`/simulation/controls/${light.id}`) && r.request().method() === 'POST');
  await lamp.getByRole('button', { name: '应用设置' }).click();
  expect((await (await lost).json()).outcome).toBe('unknown');
  await expect(lamp.getByText(/已开启 ·/)).toBeVisible();
  expect((await snapshot(request)).entities.find((e) => e.id === light.id)!.state.power).toBe(true);
  await post(request, `/faults/${light.id}`, { mode: 'delayed', delay_minutes: 2 });
  await page.getByRole('button', { name: '读取状态', exact: true }).click();
  await expect(lamp.getByRole('button', { name: '应用设置' })).toBeEnabled();
  await lamp.getByRole('switch', { name: '客厅主灯目标开关' }).click();
  await lamp.getByRole('button', { name: '应用设置' }).click();
  await expect(lamp.getByText('待第 2 分钟生效', { exact: true })).toBeVisible();
  await expect(lamp.getByText(/已开启 ·/)).toBeVisible();
  await page.getByRole('button', { name: '推进 1 分钟', exact: true }).click();
  await expect(page.getByText('已推进 1 分钟', { exact: true })).toBeVisible();
  expect((await snapshot(request)).entities.find((e) => e.id === light.id)!.state.power).toBe(true);
  await page.getByRole('button', { name: '推进 1 分钟', exact: true }).click();
  await expect(lamp.getByText('已关闭', { exact: true })).toBeVisible();
  expect((await snapshot(request)).entities.find((e) => e.id === light.id)!.pending_until_minutes).toBeNull();
});

test('390px 手机端能控制实体、打开故障和新增房间', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const lamp = page.getByRole('article', { name: '卧室主灯', exact: true });
  await lamp.getByRole('switch', { name: '卧室主灯目标开关' }).click();
  await lamp.getByRole('button', { name: '应用设置' }).click();
  await expect(lamp.getByText('已开启 · 30%', { exact: true })).toBeVisible();
  await lamp.getByRole('button', { name: '故障设置', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '卧室主灯 · 故障设置' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole('dialog', { name: '卧室主灯 · 故障设置' }).getByRole('button', { name: '关闭', exact: true }).click();
  await page.getByRole('button', { name: '家庭配置', exact: true }).last().click();
  await page.getByRole('button', { name: '新增房间', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '新增房间' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('允许的长房间名称在390px概览和配置中均不撑破页面', async ({ page, request }) => {
  await post(request, '/rooms', { name: 'W'.repeat(40) });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'W'.repeat(40), exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole('button', { name: '家庭配置', exact: true }).last().click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
