import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resetSessionContext } from './client';
import { parseDetail } from './tasks.validation';
import { TaskSubmission, tasksApi } from './tasks';
import { makeForecastTask } from '../test/forecast-fixtures';
import { makeAgentTask } from '../test/agent-fixtures';

beforeEach(() => { sessionStorage.clear(); resetSessionContext('csrf-test'); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); resetSessionContext(null); });

it('接受完整预测与旧任务，拒绝损坏的截止判断/范围/不明策略', () => {
  const task = makeForecastTask();
  expect(parseDetail(task).agent_run).toMatchObject({ selected_candidate_id: 'c1' });
  expect(() => parseDetail(makeAgentTask())).not.toThrow();
  const candidate = task.agent_run.forecast.candidates[0];
  for (const patch of [{ deadline_met: 'yes' }, { energy_wh: -1 }, { first_observed_goal_minute: 61 },
    { fan_mode: 'turbo' }, { energy_wh: Infinity }]) {
    expect(() => parseDetail({ ...task, agent_run: { ...task.agent_run,
      forecast: { ...task.agent_run.forecast, candidates: [{ ...candidate, ...patch }] } } })).toThrow(/无法识别/);
  }
  expect(() => parseDetail({ ...task, agent_run: { ...task.agent_run, selected_candidate_id: 'fiction' } })).toThrow();
  expect(() => parseDetail({ ...task, agent_run: { ...task.agent_run,
    forecast: { ...task.agent_run.forecast, candidates: Array(5).fill(candidate) } } })).toThrow();
  expect(() => parseDetail({ ...task, request: { ...task.request, strategy: 'future-unknown' } })).toThrow();
});

it('实验策略在未知响应后刷新保持原body/key，换策略不得沿用未决提交', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('lost')).mockResolvedValue(Response.json(makeForecastTask()));
  vi.stubGlobal('fetch', fetch);
  const body = { text: '60分钟26℃优先节能', expected_world_id: 'world-test', strategy: 'single_forecast' as const };
  const first = new TaskSubmission('home-forecast');
  await expect(first.submitAgent(body)).rejects.toThrow();
  const restored = new TaskSubmission('home-forecast');
  expect(restored.getSnapshot().pending).toMatchObject({ body });
  await expect(restored.submitAgent({ ...body, strategy: 'standard' })).rejects.toThrow(/原提交/);
  await restored.retryPending();
  expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[0][1].body);
  expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
});

it('未知策略的session数据不恢复成可重试的standard', () => {
  sessionStorage.setItem('homemind.tasks.v1:home-invalid', JSON.stringify({ version: 1,
    pending: { kind: 'agent', key: 'unknown-key-123', body: { text: '需求', expected_world_id: 'world-test', strategy: 'fiction' } },
    agentDraft: { text: '需求', keep_entity_ids: [], protected_room_ids: [], strategy: 'fiction' } }));
  expect(new TaskSubmission('home-invalid').getSnapshot().pending).toBeNull();
  expect(new TaskSubmission('home-invalid').getSnapshot().agentDraft.text).toBe('');
});

it('不把非法实验配置当作可用入口', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ available: true, model: 'model', reason: null,
    strategies: ['standard', 'unknown'] })));
  await expect(tasksApi.agentConfig()).rejects.toThrow(/无法识别/);
});

it('预测与本轮请求快照/目标/原选绑定，不把自洽但错误的预测渲染给用户', () => {
  const task = makeForecastTask(); const run = task.agent_run; const f = run.forecast;
  const c = f.candidates[0];
  const invalidRuns = [
    { ...run, forecast: { ...f, energy_scope_entity_ids: ['foreign-ac'] } },
    { ...run, forecast: { ...f, source: { ...f.source, revision: 1 } } },
    { ...run, goal: { ...run.goal, climate_entity_id: 'foreign-ac' } },
    { ...run, forecast: { ...f, candidates: [{ ...c, deadline_met: false }] } },
    { ...run, goal: { ...run.goal, allowed_fan_modes: ['auto'] } },
    { ...run, forecast: { ...f, candidates: [{ ...c, actions: [{ ...c.actions[0], entity_id: 'foreign-ac' }] }] } },
    { ...run, forecast: { ...f, candidates: [{ ...c, actions: [{ ...c.actions[0], parameters: { ...c.actions[0].parameters, target_temperature_c: 30 } }] }] } },
    { ...run, proposed_plan: null },
    { ...run, proposed_plan: { ...run.proposed_plan, ready_in_minutes: 20 } },
    { ...run, proposed_plan: { ...run.proposed_plan, actions: [{ ...run.proposed_plan.actions[0], room_id: 'foreign-room' }] } },
    { ...run, selected_candidate_id: null, preference_optimal: null },
  ];
  for (const invalid of invalidRuns) expect(() => parseDetail({ ...task, agent_run: invalid })).toThrow(/无法识别/);
  expect(() => parseDetail({ ...task, request: { ...task.request, strategy: 'standard' } })).toThrow();
});
