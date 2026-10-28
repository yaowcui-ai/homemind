import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import { testPassword, username, write } from './helpers';
import type { Snapshot } from '../src/api/simulation.types';
import type { TaskDetail } from '../src/api/tasks.types';

const origin = 'http://127.0.0.1:5176';
const agentWrite = (request: APIRequestContext, method: string, endpoint: string, data?: unknown) => write(request, method, endpoint, data, { Origin: origin });
async function registerAgent(request: APIRequestContext, page: Page) {
  const response = await agentWrite(request, 'POST', '/auth/register', { username: username(), password: testPassword });
  expect(response.status()).toBe(200);
  await page.context().addCookies((await request.storageState()).cookies);
  return response.json();
}
async function tasks(page: Page) {
  await page.getByRole('button', { name: '任务助手', exact: true }).filter({ visible: true }).first().click();
}
async function agent(page: Page) {
  await tasks(page);
  await page.getByRole('button', { name: '自然语言任务', exact: true }).click();
  await expect(page.getByRole('region', { name: '自然语言任务表单' })).toBeVisible();
}
async function submit(page: Page, text: string) {
  await page.getByLabel('生活需求', { exact: true }).fill(text);
  const response = page.waitForResponse((r) => r.url().endsWith('/api/tasks/agent') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '提交自然语言任务', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  const task: TaskDetail = await result.json();
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
  return task;
}
const detailRegion = (page: Page) => page.getByRole('region', { name: '任务详情' });
test.beforeEach(async ({ page, request }) => { await registerAgent(request, page); });

test('产品C2受控模型：无效澄清选项说明未执行，诊断折叠且刷新只读', async ({ page, request }) => {
  const before: Snapshot = await (await request.get('/api/simulation')).json();
  await page.goto('/'); await agent(page);
  const task = await submit(page, '受控无效选项诊断');
  expect(task).toMatchObject({ status: 'failed', actions: [], agent_run: { failure_code: 'not_found',
    diagnostic: { phase: 'validation', output_kind: 'clarify', field_path: '$.options[0].id',
      reference_kind: 'entity', reference_in_current_home: false } } });
  expect(task.agent_run?.question).toBeNull();
  expect(JSON.stringify(task)).not.toContain('confirm_closed');
  await expect(detailRegion(page).getByText(/当前方案未执行.*当前家庭.*开始新任务/)).toBeVisible();
  await expect(detailRegion(page).getByText(/\$\.options\[0\]\.id/)).toBeHidden();
  await expect(page.getByRole('button', { name: '提交补充回答' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '核验目标' })).toHaveCount(0);
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-c2-invalid-reference.png') });
  await page.getByText('运行记录与调用用量', { exact: true }).click();
  await expect(detailRegion(page).getByText(/\$\.options\[0\]\.id/)).toBeVisible();
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-c2-diagnostic-expanded.png') });
  let posts = 0;
  page.on('request', (r) => { if (r.url().includes('/api/tasks') && r.method() === 'POST') posts += 1; });
  await page.reload(); await tasks(page);
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
  await expect(detailRegion(page).getByText(/当前方案未执行.*当前家庭.*开始新任务/)).toBeVisible();
  expect(posts).toBe(0);
  expect(await (await request.get('/api/simulation')).json()).toEqual(before);
});

for (const committed of [true, false]) test(`产品C：推进响应丢失刷新只读，${committed ? '已提交原键只读恢复' : '未提交保留原键重试一次'}`, async ({ page, request }) => {
  const before: Snapshot = await (await request.get('/api/simulation')).json();
  const created = await write(request, 'POST', '/tasks', { scenario: 'sleep', room_ids: [before.rooms[0].id], target_temperature_c: 18 },
    { Origin: origin, 'Idempotency-Key': `c-sleep-${crypto.randomUUID()}` });
  expect(created.ok()).toBeTruthy();
  const task: TaskDetail = await created.json();
  await page.goto('/'); await tasks(page);
  await page.getByRole('region', { name: '任务列表' }).getByRole('button').filter({ hasText: '睡眠' }).click();
  let frozenBody: unknown; let frozenKey = ''; let posts = 0;
  page.on('request', (r) => { if (r.url().endsWith(`/tasks/${task.id}/advance`) && r.method() === 'POST') posts += 1; });
  await page.route(`**/api/tasks/${task.id}/advance`, async (route) => {
    frozenBody = route.request().postDataJSON(); frozenKey = route.request().headers()['idempotency-key'];
    if (committed) expect((await route.fetch()).ok()).toBeTruthy();
    await route.abort('failed');
  }, { times: 1 });
  await page.getByRole('button', { name: '推进 10 仿真分钟并核验' }).click();
  await expect(page.getByText('原提交结果待确认', { exact: true })).toBeVisible();
  expect(frozenKey).toBeTruthy();
  expect(frozenBody).toEqual({ expected_world_id: before.world_id, expected_simulated_minutes: 0 });
  await page.reload(); await tasks(page);
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
  if (committed) {
    await expect(page.getByText('原提交结果待确认', { exact: true })).toHaveCount(0);
    const replay = await write(request, 'POST', `/tasks/${task.id}/advance`, frozenBody, { Origin: origin, 'Idempotency-Key': frozenKey });
    expect(replay.ok()).toBeTruthy();
    expect(posts).toBe(1);
  } else {
    await expect(page.getByText('原提交结果待确认', { exact: true })).toBeVisible();
    expect(posts).toBe(1);
    const retried = page.waitForRequest((r) => r.url().endsWith(`/tasks/${task.id}/advance`) && r.method() === 'POST');
    await page.getByRole('button', { name: '同键重试原始意图' }).click();
    const sent = await retried;
    expect(sent.headers()['idempotency-key']).toBe(frozenKey); expect(sent.postDataJSON()).toEqual(frozenBody);
    await expect(page.getByText('原提交结果待确认', { exact: true })).toHaveCount(0);
  }
  const latest: Snapshot = await (await request.get('/api/simulation')).json();
  expect(latest.simulated_minutes).toBe(10);
  const final: TaskDetail = await (await request.get(`/api/tasks/${task.id}`)).json();
  expect(final.actions).toEqual(task.actions);
  expect(final.advance_records).toHaveLength(1);
  await detailRegion(page).screenshot({ path: path.resolve(`../output/product-c-advance-${committed ? 'committed' : 'retry'}.png`) });
});

test('受控模型：明确局部关灯直接执行，刷新只定位原任务', async ({ page, request }) => {
  const before: Snapshot = await (await request.get('/api/simulation')).json();
  const lamp = before.entities.find((e) => e.type === 'light' && e.room_id === before.rooms[0].id)!;
  expect((await agentWrite(request, 'POST', `/simulation/controls/${lamp.id}`, { action: 'set_light', parameters: { power: true } })).ok()).toBeTruthy();
  await page.goto('/'); await agent(page);
  const task = await submit(page, '关闭客厅主灯');
  expect(task).toMatchObject({ mode: 'single_agent', scenario: 'local', status: 'succeeded' });
  expect(task.actions).toHaveLength(1);
  expect(task.actions[0].entity_id).toBe(lamp.id);
  await expect(page.getByRole('button', { name: '确认执行此方案' })).toHaveCount(0);
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-b-agent-local.png') });
  let writes = 0;
  page.on('request', (r) => { if (r.url().includes('/api/tasks') && r.method() === 'POST') writes += 1; });
  await page.reload(); await tasks(page);
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
  expect(writes).toBe(0);
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('受控模型：澄清显示真实房间选项，补充后保持相同task_id', async ({ page }) => {
  await page.goto('/'); await agent(page);
  const initial = await submit(page, '准备一下');
  expect(initial.status).toBe('waiting_input');
  expect(initial.actions).toHaveLength(0);
  await expect(detailRegion(page).getByText('你希望操作哪个房间？', { exact: true })).toBeVisible();
  const response = page.waitForResponse((r) => r.url().endsWith(`/api/tasks/${initial.id}/reply`));
  await page.getByRole('region', { name: '补充任务信息' }).getByRole('button', { name: '客厅', exact: true }).click();
  const result = await response; expect(result.status()).toBe(200);
  const continued: TaskDetail = await result.json();
  expect(continued.id).toBe(initial.id); expect(continued.agent_run?.turn).toBe(1);
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-b-agent-clarified.png') });
});

test('受控模型：全屋方案先展示范围与实际动作，确认才执行', async ({ page, request }) => {
  await page.goto('/'); await agent(page);
  const task = await submit(page, '关闭全屋灯和空调');
  expect(task.status).toBe('waiting_confirmation'); expect(task.actions).toHaveLength(0);
  await expect(detailRegion(page).getByText(/作用房间：.*客厅.*卧室/)).toBeVisible();
  await expect(detailRegion(page).getByText(/关闭灯光/).first()).toBeVisible();
  await expect(detailRegion(page).getByText(/关闭空调/).first()).toBeVisible();
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-b-agent-confirmation.png') });
  const response = page.waitForResponse((r) => r.url().endsWith(`/api/tasks/${task.id}/confirm`));
  await page.getByRole('button', { name: '确认执行此方案' }).click();
  const actual = await response; expect(actual.status()).toBe(200);
  const confirmed: TaskDetail = await actual.json();
  expect(confirmed.id).toBe(task.id); expect(confirmed.actions).toHaveLength(4);
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('受控模型：60分钟目标在原任务推进并按目标时刻核验', async ({ page, request }) => {
  await page.goto('/'); await agent(page);
  const task = await submit(page, '60个仿真分钟后回家，客厅准备到26℃');
  expect(task.status).toBe('waiting_verification');
  await expect(detailRegion(page).getByText(/当前仿真时刻 t\+0 分钟.*目标时刻 t\+60 分钟/)).toBeVisible();
  const response = page.waitForResponse((r) => r.url().endsWith(`/api/tasks/${task.id}/advance`));
  await page.getByRole('button', { name: '推进至目标时刻 t+60 分钟并核验', exact: true }).click();
  const actual = await response; expect(actual.status()).toBe(200);
  const advanced: TaskDetail = await actual.json();
  expect(advanced.verification.checked_at_minutes).toBe(60);
  expect(advanced.actions.map((a) => a.id)).toEqual(task.actions.map((a) => a.id));
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
  await detailRegion(page).screenshot({ path: path.resolve('../output/product-b-agent-future.png') });
  const latest: TaskDetail = await (await request.get(`/api/tasks/${task.id}`)).json();
  expect(latest.final_snapshot.simulated_minutes).toBe(60);
});

test('受控模型：创建响应丢失刷新后只GET提交键并定位原任务', async ({ page, request }) => {
  let taskId = ''; let writes = 0; let keyReads = 0;
  await page.route('**/api/tasks/agent', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    writes += 1;
    const committed = await route.fetch(); expect(committed.status()).toBe(200);
    taskId = (await committed.json()).id;
    await route.abort('failed');
  });
  page.on('request', (r) => { if (r.url().includes('/api/tasks?submission_key=')) keyReads += 1; });
  await page.goto('/'); await agent(page);
  await page.getByLabel('生活需求').fill('关闭客厅主灯');
  await page.getByRole('button', { name: '提交自然语言任务' }).click();
  await expect(page.getByText('原提交结果待确认', { exact: true })).toBeVisible();
  await page.reload(); await tasks(page);
  await expect(page.getByText(`任务编号 ${taskId}`, { exact: true })).toBeVisible();
  await expect(page.getByText('原提交结果待确认', { exact: true })).toHaveCount(0);
  expect(writes).toBe(1); expect(keyReads).toBeGreaterThan(0);
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('受控模型：未找到未知提交时显式同键重试原意图，世界读取不改正文', async ({ page, request }) => {
  const sent: { key: string; body: string | null }[] = [];
  await page.route('**/api/tasks/agent', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    sent.push({ key: route.request().headers()['idempotency-key'], body: route.request().postData() });
    if (sent.length === 1) { expect((await route.fetch()).status()).toBe(200); await route.abort('failed'); }
    else await route.continue();
  });
  // Model a temporarily unavailable lookup without making a second write automatically.
  await page.route('**/api/tasks?submission_key=*', (route) => route.fulfill({ json: [] }));
  await page.goto('/'); await agent(page);
  await page.getByLabel('生活需求').fill('关闭客厅主灯');
  await page.getByRole('button', { name: '提交自然语言任务' }).click();
  await expect(page.getByText('原提交结果待确认', { exact: true })).toBeVisible();
  await page.reload(); await tasks(page);
  await expect(page.getByRole('button', { name: '同键重试原始意图' })).toBeEnabled();
  expect(sent).toHaveLength(1);
  await page.getByRole('button', { name: '同键重试原始意图' }).click();
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
  expect(sent).toHaveLength(2); expect(sent[1]).toEqual(sent[0]);
  expect((await (await request.get('/api/tasks')).json()).length).toBe(1);
});

test('受控模型：回复响应丢失刷新只读原任务，不自动回答第二次', async ({ page }) => {
  await page.goto('/'); await agent(page);
  const task = await submit(page, '准备一下'); let replies = 0;
  await page.route(`**/api/tasks/${task.id}/reply`, async (route) => {
    replies += 1; expect((await route.fetch()).status()).toBe(200); await route.abort('failed');
  });
  await page.getByRole('region', { name: '补充任务信息' }).getByRole('button', { name: '客厅', exact: true }).click();
  await expect(page.getByText('原提交结果待确认', { exact: true })).toBeVisible();
  await page.reload(); await tasks(page);
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
  expect(replies).toBe(1);
});

test('自然语言草稿和任务定位按家庭隔离，重新登录只读取自己的任务', async ({ page, request }) => {
  const session = await (await request.get('/api/auth/session')).json();
  await page.goto('/'); await agent(page);
  const task = await submit(page, '关闭客厅主灯');
  await page.getByLabel('生活需求').fill('账号甲的私有需求草稿');
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '欢迎回家' })).toBeVisible();
  await registerAgent(request, page); await page.reload(); await agent(page);
  await expect(page.getByLabel('生活需求')).toHaveValue('');
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await page.getByLabel('用户名', { exact: true }).fill(session.user.username);
  await page.getByLabel('密码', { exact: true }).fill(testPassword);
  await page.getByRole('button', { name: '登录我的家庭' }).click();
  await agent(page);
  await expect(page.getByLabel('生活需求')).toHaveValue('账号甲的私有需求草稿');
  await expect(page.getByText(`任务编号 ${task.id}`, { exact: true })).toBeVisible();
});

for (const width of [360, 390]) test(`受控模型：${width}px任务确认可操作且无横向溢出`, async ({ page }) => {
  await page.setViewportSize({ width, height: 844 });
  await page.goto('/'); await agent(page);
  await submit(page, '关闭全屋灯和空调');
  await expect(page.getByRole('button', { name: '确认执行此方案' })).toBeEnabled();
  await detailRegion(page).getByText('运行记录与调用用量', { exact: true }).click();
  await expect(detailRegion(page).getByText(/实际模型：controlled-browser-test/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({ path: path.resolve(`../output/product-b-agent-mobile-${width}.png`), fullPage: true });
  await page.getByRole('button', { name: '确认执行此方案' }).click();
  await expect(detailRegion(page).getByText('全部条件已核验', { exact: true })).toBeVisible();
});
