import { afterEach, describe, expect, it, vi } from 'vitest';
import { resetSessionContext } from './client';
import { TaskSubmission } from './tasks';
import type { RuleRequest } from './tasks.types';
import { makeSnapshot } from '../test/simulation-fixtures';

afterEach(() => { resetSessionContext(null); vi.unstubAllGlobals(); });
const body: RuleRequest = { scenario: 'away', room_ids: ['room-1'] };
const detail = { id: 'task-1', scenario: 'away', status: 'succeeded', created_at: 1, updated_at: 1,
  world_id: 'world-test', message: '完成', request: body,
  preferences_snapshot: { version: 1, comfort_temperature_c: 26, sleep_temperature_c: 27, fan_mode: 'low', arrival_lead_minutes: 20 },
  initial_snapshot: makeSnapshot(), final_snapshot: makeSnapshot(), actions: [],
  verification: { due_at_minutes: null, checked_at_minutes: 0, conditions: [] } };

describe('规则任务提交', () => {
  it('超时/网络失败后同内容重试复用幂等键，成功后的新任务使用新键', async () => {
    resetSessionContext('csrf-test');
    const fetch = vi.fn().mockRejectedValueOnce(new Error('private transport'))
      .mockImplementation(() => Promise.resolve(Response.json(detail)));
    vi.stubGlobal('fetch', fetch);
    const submission = new TaskSubmission();
    await expect(submission.submit(body)).rejects.toThrow(/连接/);
    await submission.submit(body);
    await submission.submit(body);
    const keys = fetch.mock.calls.map((call) => (call[1] as RequestInit).headers as Record<string, string>).map((h) => h['Idempotency-Key']);
    expect(keys[0]).toBe(keys[1]); expect(keys[2]).not.toBe(keys[1]);
  });
});
