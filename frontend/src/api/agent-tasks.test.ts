import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, resetSessionContext } from './client';
import { TaskSubmission, tasksApi } from './tasks';
import { makeAgentTask } from '../test/agent-fixtures';
import { makeTask } from '../test/simulation-fixtures';

beforeEach(() => { sessionStorage.clear(); resetSessionContext('test-csrf'); });
afterEach(() => { resetSessionContext(null); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe('自然语言任务和刷新恢复', () => {
  it('创建晚到结果不抢回用户显式选择的其他历史任务', async () => {
    let finish!: (task: ReturnType<typeof makeTask>) => void;
    vi.spyOn(tasksApi, 'create').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const submission = new TaskSubmission('home-a');
    submission.select('task-old');
    const pending = submission.submit({ scenario: 'away', room_ids: ['room-1'] });
    submission.select('task-user-chosen');
    finish(makeTask({ id: 'task-new' })); await pending;
    expect(submission.getSnapshot().selectedId).toBe('task-user-chosen');
  });

  it('恢复期间用户切换A到B再回A，晚到新任务仍不抢选且原提交已定位', async () => {
    vi.spyOn(tasksApi, 'create').mockRejectedValue(new Error('lost'));
    const original = new TaskSubmission('home-a'); original.select('task-old');
    await expect(original.submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toThrow();
    vi.spyOn(tasksApi, 'list').mockResolvedValue([makeTask({ id: 'task-new' })]);
    let finish!: (task: ReturnType<typeof makeTask>) => void;
    vi.spyOn(tasksApi, 'get').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const restored = new TaskSubmission('home-a');
    const pending = restored.recover();
    restored.select('task-other'); restored.select('task-old');
    finish(makeTask({ id: 'task-new' })); await pending;
    expect(restored.getSnapshot()).toMatchObject({ selectedId: 'task-old', pending: null });
  });

  it('旧恢复跨过完整的新写入后失效，不用相同null状态覆盖新任务定位', async () => {
    const submission = new TaskSubmission('home-a'); submission.select('task-old');
    let finish!: (task: ReturnType<typeof makeTask>) => void;
    vi.spyOn(tasksApi, 'get').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    vi.spyOn(tasksApi, 'create').mockResolvedValue(makeTask({ id: 'task-new' }));
    const read = submission.recover();
    await submission.submit({ scenario: 'away', room_ids: ['room-1'] });
    finish(makeTask({ id: 'task-old' }));
    expect(await read).toBeNull();
    expect(submission.getSnapshot().selectedId).toBe('task-new');
  });

  it('接受没有scenario的Agent请求与真实等待补充状态', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(makeAgentTask())));
    await expect(tasksApi.get('task-1')).resolves.toMatchObject({ mode: 'single_agent', status: 'waiting_input' });
  });

  it('兼容无诊断旧任务，并校验新增有限诊断类型', async () => {
    const task = makeAgentTask();
    const diagnostic = { phase: 'validation', output_kind: 'clarify', code: 'not_found',
      field_path: '$.options[0].id', reference_kind: 'entity', reference_in_current_home: false };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(task))
      .mockResolvedValueOnce(Response.json({ ...task, agent_run: { ...task.agent_run, diagnostic } }))
      .mockResolvedValueOnce(Response.json({ ...task, agent_run: { ...task.agent_run,
        diagnostic: { ...diagnostic, reference_in_current_home: 'false' } } })));
    await expect(tasksApi.get('task-1')).resolves.toMatchObject({ mode: 'single_agent' });
    await expect(tasksApi.get('task-1')).resolves.toMatchObject({ agent_run: { diagnostic } });
    await expect(tasksApi.get('task-1')).rejects.toThrow(/无法识别/);
  });

  it('自然语言配置只报告配置状态，不把缺失reason接受为合法响应', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ available: true, model: 'configured-model', reason: null })));
    await expect(tasksApi.agentConfig()).resolves.toEqual({ available: true, model: 'configured-model', reason: null });
  });

  it('拒绝损坏的Agent硬约束，不能让详情渲染把字符串当设备数组', async () => {
    const invalid = { ...makeAgentTask(), request: { text: '关灯', expected_world_id: 'world-test', keep_entity_ids: 'invalid-array' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(invalid)));
    await expect(tasksApi.get('task-1')).rejects.toThrow(/无法识别/);
  });

  it('刷新后未知规则提交复用冻结的原始请求和同一键', async () => {
    const original = { scenario: 'away' as const, room_ids: ['room-1'], expected_world_id: 'old-world' };
    const fetch = vi.fn().mockRejectedValueOnce(new Error('lost response')).mockResolvedValue(Response.json(makeTask()));
    vi.stubGlobal('fetch', fetch);
    await expect(new TaskSubmission('home-a').submit(original)).rejects.toThrow();
    const refreshed = new TaskSubmission('home-a');
    await refreshed.retryPending();
    expect(fetch.mock.calls[1][1].body).toBe(JSON.stringify(original));
    expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
  });

  it('刷新恢复创建只GET查提交键及原任务，找到即定位且不会POST', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('lost response'));
    vi.stubGlobal('fetch', fetch);
    await expect(new TaskSubmission('home-a').submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toThrow();
    fetch.mockResolvedValueOnce(Response.json([makeTask()])).mockResolvedValueOnce(Response.json(makeTask()));
    const refreshed = new TaskSubmission('home-a');
    await refreshed.recover();
    expect(refreshed.getSnapshot()).toMatchObject({ selectedId: 'task-1', pending: null });
    expect(fetch.mock.calls.slice(1).every((call) => call[1].method === 'GET')).toBe(true);
    expect(fetch.mock.calls[1][0]).toContain('/tasks?submission_key=');
  });

  it('未知回复刷新先GET原task，没有接受回答时保留同键重试', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('lost reply'));
    vi.stubGlobal('fetch', fetch);
    const submission = new TaskSubmission('home-a');
    await expect(submission.reply('task-1', { text: '客厅', expected_turn: 0 })).rejects.toThrow();
    fetch.mockResolvedValueOnce(Response.json(makeAgentTask()));
    const refreshed = new TaskSubmission('home-a');
    await refreshed.recover();
    expect(refreshed.getSnapshot().pending?.kind).toBe('reply');
    fetch.mockResolvedValueOnce(Response.json(makeAgentTask({ status: 'succeeded' })));
    await refreshed.retryPending();
    expect(fetch.mock.calls[2][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
    expect(fetch.mock.calls[1][1].method).toBe('GET');
  });

  it('未知确认刷新先GET原方案，仍待确认时重试保持原键和轮次', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('lost confirmation'));
    vi.stubGlobal('fetch', fetch);
    await expect(new TaskSubmission('home-a').confirm('task-1', { expected_turn: 0 })).rejects.toThrow();
    fetch.mockResolvedValueOnce(Response.json(makeAgentTask({ status: 'waiting_confirmation' })));
    const refreshed = new TaskSubmission('home-a');
    await refreshed.recover();
    expect(refreshed.getSnapshot().pending?.kind).toBe('confirm');
    expect(fetch.mock.calls[1][1].method).toBe('GET');
    fetch.mockResolvedValueOnce(Response.json(makeAgentTask({ status: 'succeeded' })));
    await refreshed.retryPending();
    expect(fetch.mock.calls[2][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ expected_turn: 0 });
  });

  it('账号家庭隔离且损坏/受限sessionStorage不会导致崩溃', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('lost')); vi.stubGlobal('fetch', fetch);
    await expect(new TaskSubmission('home-a').submit({ scenario: 'away', room_ids: ['private-a'] })).rejects.toThrow();
    expect(new TaskSubmission('home-b').getSnapshot().pending).toBeNull();
    sessionStorage.setItem('homemind.tasks.v1:home-b', '{broken');
    expect(() => new TaskSubmission('home-b')).not.toThrow();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(() => new TaskSubmission('home-c')).not.toThrow();
  });

  it('已知HTTP拒绝可重新编辑；未知提交不能因世界变化静默换键', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: { code: 'world_changed', message: '已重置' } }, { status: 409 })));
    const rejected = new TaskSubmission('home-a');
    await expect(rejected.submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toBeInstanceOf(ApiError);
    expect(rejected.getSnapshot().pending).toBeNull();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('lost')));
    const submission = new TaskSubmission('home-b');
    await expect(submission.submit({ scenario: 'away', room_ids: ['room-1'], expected_world_id: 'old' })).rejects.toThrow();
    await expect(submission.submit({ scenario: 'away', room_ids: ['room-1'], expected_world_id: 'new' })).rejects.toThrow(/原|结果|新任务/);
  });

  it('503响应仍可能发生在提交之后，刷新重试必须保留原键', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({ detail: { code: 'service_unavailable', message: '结果待确认' } }, { status: 503 }))
      .mockResolvedValueOnce(Response.json(makeTask()));
    vi.stubGlobal('fetch', fetch);
    await expect(new TaskSubmission('home-a').submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toThrow();
    const refreshed = new TaskSubmission('home-a');
    expect(refreshed.getSnapshot().pending).not.toBeNull();
    await refreshed.retryPending();
    expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
  });

  it('Agent请求可超过8秒，普通读取仍8秒超时', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('', 'AbortError')));
    })));
    const agent = new TaskSubmission('home-a').submitAgent({ text: '关灯', expected_world_id: 'world-test' });
    const ordinary = expect(tasksApi.get('task-1')).rejects.toThrow(/超时/);
    const agentResult = expect(agent).rejects.toThrow(/超时/);
    await vi.advanceTimersByTimeAsync(8000); await ordinary;
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(72000); await agentResult;
  });
});
