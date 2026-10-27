import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import TasksPanel from './TasksPanel';
import { resetSessionContext } from '../../api/client';
import { tasksApi, TaskSubmission } from '../../api/tasks';
import { makeTask } from '../../test/simulation-fixtures';

afterEach(() => { resetSessionContext(null); sessionStorage.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('同一会话切页回任务页保留未知规则原键，刷新恢复才自动按键查找', async () => {
  resetSessionContext('csrf');
  const fetch = vi.fn().mockRejectedValueOnce(new Error('lost'));
  vi.stubGlobal('fetch', fetch);
  const submission = new TaskSubmission('navigation-home');
  await expect(submission.submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toThrow();
  const task = makeTask();
  fetch.mockImplementation((url: string) => {
    const value = url.includes('agent/config') ? { available: false, model: 'model', reason: '未配置' }
      : url.includes('/preferences') ? task.preferences_snapshot
      : url.includes('/simulation') ? task.final_snapshot
      : url.includes('/tasks/task-1') ? task : [task];
    return Promise.resolve(Response.json(value));
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><TasksPanel homeId="navigation-home" submission={submission} debugEnabled /></QueryClientProvider>);
  await screen.findByRole('button', { name: '执行规则任务' });
  await waitFor(() => expect(screen.getByRole('button', { name: '读取任务' })).not.toHaveClass('ant-btn-loading'));
  expect(submission.getSnapshot().pending).not.toBeNull();
  expect(fetch.mock.calls.filter((call) => String(call[0]).includes('submission_key='))).toHaveLength(0);
  view.unmount(); client.clear();
});

it('已有storage的初始恢复只执行一次，后续新未知提交切页仍保留原键', async () => {
  resetSessionContext('csrf');
  const task = makeTask();
  const first = new TaskSubmission('restored-home'); first.select(task.id);
  const submission = new TaskSubmission('restored-home');
  const fetch = vi.fn().mockResolvedValue(Response.json(task)); vi.stubGlobal('fetch', fetch);
  await submission.recover();
  fetch.mockRejectedValueOnce(new Error('lost new submission'));
  await expect(submission.submit({ scenario: 'away', room_ids: ['room-1'] })).rejects.toThrow();
  const originalKey = submission.getSnapshot().pending?.key;
  fetch.mockImplementation((url: string) => Promise.resolve(Response.json(url.includes('agent/config')
    ? { available: false, model: 'model', reason: '未配置' } : url.includes('/preferences') ? task.preferences_snapshot
      : url.includes('/simulation') ? task.final_snapshot : url.includes('/tasks/task-1') ? task : [task])));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><TasksPanel homeId="restored-home" submission={submission} debugEnabled /></QueryClientProvider>);
  await screen.findByRole('button', { name: '执行规则任务' });
  await waitFor(() => expect(screen.getByRole('button', { name: '读取任务' })).not.toHaveClass('ant-btn-loading'));
  expect(submission.getSnapshot().pending?.key).toBe(originalKey);
  expect(fetch.mock.calls.filter((call) => String(call[0]).includes('submission_key='))).toHaveLength(0);
  view.unmount(); client.clear();
});

it('核验晚到结果只更新缓存，不抢回用户正在浏览的另一任务', async () => {
  resetSessionContext('csrf');
  const taskA = makeTask({ id: 'task-a' }); const taskB = makeTask({ id: 'task-b' });
  let finish!: (task: ReturnType<typeof makeTask>) => void;
  vi.spyOn(tasksApi, 'verify').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(Response.json(url.includes('agent/config')
    ? { available: false, model: 'model', reason: '未配置' } : url.includes('/preferences') ? taskA.preferences_snapshot
      : url.includes('/simulation') ? taskA.final_snapshot : url.includes('/tasks/task-a') ? taskA : url.includes('/tasks/task-b') ? taskB : [taskA, taskB]))));
  const submission = new TaskSubmission('selection-home'); submission.select(taskA.id);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><TasksPanel homeId="selection-home" submission={submission} debugEnabled /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '核验目标' }));
  fireEvent.click(within(screen.getByRole('region', { name: '任务列表' })).getAllByRole('button', { name: /离家模式/ })[1]);
  await screen.findByText('任务编号 task-b');
  await act(async () => { finish(makeTask({ id: 'task-a', status: 'succeeded' })); });
  await waitFor(() => expect(screen.getByRole('button', { name: '读取任务' })).toBeEnabled());
  expect(submission.getSnapshot().selectedId).toBe('task-b');
  expect(screen.getByText('任务编号 task-b')).toBeVisible();
  view.unmount(); client.clear();
});

it('推进请求未返回时切页重挂仍禁用推进，不发送第二条推进命令', async () => {
  resetSessionContext('csrf');
  const task = makeTask({ scenario: 'sleep', status: 'waiting_verification', request: { scenario: 'sleep', room_ids: ['room-1'] },
    actions: [{ id: 'action-1', entity_id: 'climate-1', entity_name: '空调', room_name: '客厅', action: 'set_climate',
      parameters: { mode: 'cool', target_temperature_c: 26 }, status: 'verified', transport_outcome: 'verified', message: '已读回' }],
    plan: { actions: [], constraints: [], temperatures: [{ room_id: 'room-1', room_name: '客厅', target: 26 }], due_at_minutes: null } });
  let finish!: (task: ReturnType<typeof makeTask>) => void;
  const advance = vi.spyOn(tasksApi, 'advance').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(Response.json(url.includes('agent/config')
    ? { available: false, model: 'model', reason: '未配置' } : url.includes('/preferences') ? task.preferences_snapshot
      : url.includes('/simulation') ? task.final_snapshot : url.includes('/tasks/task-1') ? task : [task]))));
  const submission = new TaskSubmission('advance-home'); submission.select(task.id);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const panel = <QueryClientProvider client={client}><TasksPanel homeId="advance-home" submission={submission} debugEnabled /></QueryClientProvider>;
  let view = render(panel);
  fireEvent.click(await screen.findByRole('button', { name: '推进 10 仿真分钟并核验' }));
  view.unmount(); view = render(panel);
  try {
    const button = await screen.findByRole('button', { name: '推进 10 仿真分钟并核验' });
    expect(button).toBeDisabled(); fireEvent.click(button);
    expect(advance).toHaveBeenCalledOnce();
  } finally {
    await act(async () => { finish(task); }); view.unmount(); client.clear();
  }
});

it.each(['核验保存', '初始恢复'])('%s前的旧详情GET晚到不能把成功状态倒退为partial', async (mode) => {
  resetSessionContext('csrf');
  const task = makeTask({ message: 'OLD PARTIAL' }); const latest = makeTask({ status: 'succeeded', message: 'NEW VERIFIED' });
  const previous = new TaskSubmission('stale-home'); previous.select(task.id);
  const submission = mode === '初始恢复' ? new TaskSubmission('stale-home') : previous;
  let finish!: (task: ReturnType<typeof makeTask>) => void;
  vi.spyOn(tasksApi, 'get').mockReturnValueOnce(new Promise((resolve) => { finish = resolve; })).mockResolvedValue(latest);
  vi.spyOn(tasksApi, 'verify').mockResolvedValue(latest);
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(Response.json(url.includes('agent/config')
    ? { available: false, model: 'model', reason: '未配置' } : url.includes('/preferences') ? task.preferences_snapshot
      : url.includes('/simulation') ? task.final_snapshot : [task]))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const key = ['task', 'stale-home', task.id]; client.setQueryData(key, task);
  const view = render(<QueryClientProvider client={client}><TasksPanel homeId="stale-home" submission={submission} debugEnabled /></QueryClientProvider>);
  if (mode === '核验保存') fireEvent.click(await screen.findByRole('button', { name: '核验目标' }));
  await screen.findByText('NEW VERIFIED');
  await act(async () => { finish(task); });
  expect(client.getQueryData(key)).toMatchObject({ status: 'succeeded', message: 'NEW VERIFIED' });
  expect(screen.getByText('NEW VERIFIED')).toBeVisible();
  view.unmount(); client.clear();
});

it('恢复取消旧GET的等待间隙发生新核验时，不再写回旧恢复快照', async () => {
  resetSessionContext('csrf');
  const task = makeTask({ message: 'OLD PARTIAL' }); const latest = makeTask({ status: 'succeeded', message: 'NEW VERIFIED' });
  const previous = new TaskSubmission('cancel-home'); previous.select(task.id);
  const submission = new TaskSubmission('cancel-home');
  vi.spyOn(tasksApi, 'get').mockResolvedValue(task); vi.spyOn(tasksApi, 'verify').mockResolvedValue(latest);
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(Response.json(url.includes('agent/config')
    ? { available: false, model: 'model', reason: '未配置' } : url.includes('/preferences') ? task.preferences_snapshot
      : url.includes('/simulation') ? task.final_snapshot : [task]))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let release!: () => void;
  const cancel = vi.spyOn(client, 'cancelQueries').mockReturnValue(new Promise((resolve) => { release = resolve; }));
  const key = ['task', 'cancel-home', task.id]; client.setQueryData(key, task);
  const view = render(<QueryClientProvider client={client}><TasksPanel homeId="cancel-home" submission={submission} debugEnabled /></QueryClientProvider>);
  try {
    await waitFor(() => expect(cancel).toHaveBeenCalledWith({ queryKey: key, exact: true }));
    await act(async () => { await submission.verify(task.id); client.setQueryData(key, latest); });
    await act(async () => { release(); });
    expect(client.getQueryData(key)).toMatchObject({ status: 'succeeded', message: 'NEW VERIFIED' });
  } finally { release(); view.unmount(); client.clear(); }
});
