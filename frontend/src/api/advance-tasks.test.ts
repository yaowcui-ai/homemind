import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resetSessionContext } from './client';
import { TaskSubmission } from './tasks';
import { makeTask } from '../test/simulation-fixtures';

beforeEach(() => { sessionStorage.clear(); resetSessionContext('csrf'); });
afterEach(() => { vi.unstubAllGlobals(); resetSessionContext(null); });

const body = { expected_world_id: 'world-test', expected_simulated_minutes: 0 };

it('推进503冻结原体原键，刷新GET没有记录时保留pending且原键可重试', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(Response.json({}, { status: 503 }));
  vi.stubGlobal('fetch', fetch);
  const original = { ...body };
  await expect(new TaskSubmission('home-c').advance('task-1', original)).rejects.toThrow();
  original.expected_simulated_minutes = 10;
  const refreshed = new TaskSubmission('home-c');
  expect(refreshed.getSnapshot().pending).toMatchObject({ kind: 'advance', body });
  fetch.mockResolvedValueOnce(Response.json(makeTask()));
  await refreshed.recover();
  expect(refreshed.getSnapshot().pending?.kind).toBe('advance');
  expect(fetch.mock.calls[1][1].method).toBe('GET');
  fetch.mockResolvedValueOnce(Response.json(makeTask()));
  await refreshed.retryPending();
  expect(fetch.mock.calls[2][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
  expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual(body);
});

it('刷新只有匹配原key和body公开记录才释放推进pending，不因时间已变误判', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('response lost'));
  vi.stubGlobal('fetch', fetch);
  const submission = new TaskSubmission('home-c');
  await expect(submission.advance('task-1', body)).rejects.toThrow();
  const pending = submission.getSnapshot().pending!;
  const refreshed = new TaskSubmission('home-c');
  fetch.mockResolvedValueOnce(Response.json({ ...makeTask(), advance_records: [{ key: pending.key,
    request: { ...body, expected_simulated_minutes: 10 }, advanced_to_minutes: 20 }] }));
  await refreshed.recover();
  expect(refreshed.getSnapshot().pending?.kind).toBe('advance');
  fetch.mockResolvedValueOnce(Response.json({ ...makeTask(), advance_records: [{ key: pending.key, request: body, advanced_to_minutes: 10 }] }));
  await refreshed.recover();
  expect(refreshed.getSnapshot().pending).toBeNull();
  expect(fetch.mock.calls.slice(1).every((call) => call[1].method === 'GET')).toBe(true);
});
