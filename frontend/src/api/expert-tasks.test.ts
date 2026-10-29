import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { parseDetail } from './tasks.validation';
import { resetSessionContext } from './client';
import { TaskSubmission, tasksApi } from './tasks';
import { makeExpertTask } from '../test/expert-fixtures';
import { makeAgentTask } from '../test/agent-fixtures';

beforeEach(() => { sessionStorage.clear(); resetSessionContext('csrf-test'); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); resetSessionContext(null); });

it('识别实际multi模式及本轮四阶段，保留旧单Agent响应', () => {
  const task = makeExpertTask();
  expect(parseDetail(task)).toMatchObject({ mode: 'multi_agent', agent_run: { strategy: 'expert_forecast' } });
  expect(() => parseDetail(makeAgentTask())).not.toThrow();
  expect(() => parseDetail({ ...task, mode: 'single_agent' })).toThrow();
});

it('非法角色、引用、phantom调用及不完整专家不得作为已完成协作解析', () => {
  const task = makeExpertTask(); const run = task.agent_run; const records = run.role_runs;
  const invalidRoles = [
    [records[0], records[2], records[1], records[3]],
    [records[0], { ...records[1], advice: { ...records[1].advice, role: 'energy' } }, records[2], records[3]],
    [records[0], { ...records[1], advice: { ...records[1].advice, preferred_candidate_id: 'fiction' } }, records[2], records[3]],
    [records[0], { ...records[1], advice: { ...records[1].advice, evidence_refs: ['candidate:fiction'] } }, records[2], records[3]],
    [records[0], { ...records[1], status: 'skipped' }, records[2], records[3]],
    [records[0], { ...records[1], model_calls: 2 }, records[2], records[3]],
    [records[0], records[1], records[2]],
  ];
  for (const role_runs of invalidRoles) expect(() => parseDetail({ ...task, agent_run: { ...run, role_runs } })).toThrow(/无法识别/);
  expect(() => parseDetail({ ...task, agent_run: { ...run, model_calls: 5 } })).toThrow();
  expect(() => parseDetail({ ...task, agent_run: { ...run, pipeline_version: 'future-unknown' } })).toThrow();
});

it('M未知补答刷新先GET，保留原key/body，不能因不是single而清掉未决回答', async () => {
  const task = makeExpertTask();
  const waiting = { ...task, status: 'waiting_input', agent_run: { ...task.agent_run, proposed_plan: null,
    selected_candidate_id: null, preference_optimal: null, question: '请选择优先级' } };
  const fetch = vi.fn().mockRejectedValueOnce(new Error('lost')).mockResolvedValueOnce(Response.json(waiting))
    .mockResolvedValueOnce(Response.json(task));
  vi.stubGlobal('fetch', fetch);
  await expect(new TaskSubmission('expert-home').reply(task.id, { text: '能耗优先', expected_turn: 0 })).rejects.toThrow();
  const restored = new TaskSubmission('expert-home');
  await restored.recover();
  expect(restored.getSnapshot().pending).toMatchObject({ kind: 'reply', body: { text: '能耗优先', expected_turn: 0 } });
  await restored.retryPending();
  expect(fetch.mock.calls[1][1].method).toBe('GET');
  expect(fetch.mock.calls[2][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
});

it('支持三种公开策略但未知策略仍拒绝', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ available: true, model: 'model', reason: null,
    strategies: ['standard', 'single_forecast', 'expert_forecast'] })));
  await expect(tasksApi.agentConfig()).resolves.toMatchObject({ strategies: ['standard', 'single_forecast', 'expert_forecast'] });
});

it('拒绝失败分析伪装可执行状态、历史夹带Advice和重复轮次计数', () => {
  const task = makeExpertTask(); const run = task.agent_run; const round = run.rounds[0];
  const failedRoles = run.role_runs.map((r, i) => i === 1 ? { ...r, status: 'failed', failure_code: 'invalid_advice', advice: null } : r);
  const metrics = failedRoles.map((r) => Object.fromEntries(Object.entries(r).filter(([key]) => key !== 'advice')));
  const refusing = run.role_runs.map((r, i) => i === 1 ? { ...r, advice: { ...r.advice,
    role: 'comfort', outcome: 'refuse', preferred_candidate_id: null, evidence_refs: ['goal'], public_summary: '不支持此任务' } } : r);
  const invalids = [
    { ...task, status: 'succeeded' },
    { ...task, agent_run: { ...run, failure_code: 'analysis_incomplete' } },
    { ...task, status: 'succeeded', agent_run: { ...run, role_runs: failedRoles,
      rounds: [{ ...round, roles: metrics }] } },
    { ...task, status: 'succeeded', agent_run: { ...run, role_runs: refusing } },
    { ...task, agent_run: { ...run, rounds: [{ ...round, roles: round.roles.map((r, i) => i === 1
      ? { ...r, advice: { preferred_candidate_id: 'old-foreign-candidate' } } : r) }] } },
    { ...task, agent_run: { ...run, model_calls: 8, rounds: [round, round] } },
    { ...task, agent_run: { ...run, turn: 1, rounds: [{ ...round, turn: 1 }] } },
    { ...task, status: 'failed', agent_run: { ...run, failure_code: 'analysis_incomplete', role_runs: [], rounds: [], model_calls: 0 } },
  ];
  for (const invalid of invalids) expect(() => parseDetail(invalid)).toThrow(/无法识别/);
});

it('尚未启动阶段的planning与早期取消保留空账本，不虚构角色调用', () => {
  const task = makeExpertTask();
  for (const status of ['planning', 'failed']) {
    const data = { ...task, status, plan: { actions: [], constraints: [], temperatures: [], due_at_minutes: null }, agent_run: {
      ...task.agent_run, role_runs: [], rounds: [], model_calls: 0, tool_calls: 0, actual_model: null,
      goal: null, forecast: null, proposed_plan: null, selected_candidate_id: null, preference_optimal: null,
      failure_code: status === 'failed' ? 'request_cancelled' : null } };
    expect(() => parseDetail(data)).not.toThrow();
  }
});
