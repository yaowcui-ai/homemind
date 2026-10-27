import { apiRequest, isObject, isNumber, isText } from './client';
import { isPreferences } from './preferences';
import { isSnapshot } from './simulation';
import type { RuleRequest, TaskDetail, TaskSummary } from './tasks.types';

const scenarios = ['homecoming', 'sleep', 'away'];
const statuses = ['queued', 'running', 'waiting_input', 'waiting_verification', 'succeeded', 'partial', 'failed', 'cancelled'];
function isSummary(data: unknown): data is TaskSummary {
  return isObject(data) && isText(data.id) && scenarios.includes(String(data.scenario)) && statuses.includes(String(data.status))
    && isNumber(data.created_at) && isNumber(data.updated_at) && isText(data.world_id) && typeof data.message === 'string';
}
function isDetail(data: unknown): data is TaskDetail {
  if (!isSummary(data) || !isObject(data)) return false;
  const value: Record<string, unknown> = data;
  return isObject(value.request) && scenarios.includes(String(value.request.scenario)) && Array.isArray(value.request.room_ids)
    && value.request.room_ids.every(isText) && isPreferences(value.preferences_snapshot)
    && isSnapshot(value.initial_snapshot) && isSnapshot(value.final_snapshot) && Array.isArray(value.actions)
    && value.actions.every((a) => isObject(a) && isText(a.id) && isText(a.entity_id) && isText(a.entity_name)
      && isText(a.room_name) && isText(a.action) && isObject(a.parameters)
      && ['planned', 'submitted', 'verified', 'failed', 'unknown', 'skipped'].includes(String(a.status))
      && (a.transport_outcome === null || isText(a.transport_outcome)) && typeof a.message === 'string')
    && isObject(value.verification) && (value.verification.due_at_minutes === null || isNumber(value.verification.due_at_minutes))
    && isNumber(value.verification.checked_at_minutes) && Array.isArray(value.verification.conditions)
    && value.verification.conditions.every((c) => isObject(c) && isText(c.label) && typeof c.message === 'string'
      && ['verified', 'failed', 'unknown', 'pending'].includes(String(c.outcome)));
}
async function detail(path: string, method = 'GET', body?: unknown, headers?: Record<string, string>): Promise<TaskDetail> {
  const data = await apiRequest(path, method, body, headers);
  if (!isDetail(data)) throw new Error('服务返回了无法识别的任务信息。');
  return data;
}
export const tasksApi = {
  async list(): Promise<TaskSummary[]> {
    const data = await apiRequest('/tasks');
    if (!Array.isArray(data) || !data.every(isSummary)) throw new Error('服务返回了无法识别的任务列表。');
    return data;
  },
  get: (id: string) => detail(`/tasks/${encodeURIComponent(id)}`),
  verify: (id: string) => detail(`/tasks/${encodeURIComponent(id)}/verify`, 'POST', {}),
  create: (body: RuleRequest, key: string) => detail('/tasks', 'POST', body, { 'Idempotency-Key': key }),
};

export class TaskSubmission {
  private fingerprint = '';
  private key = '';
  private completed = false;
  async submit(body: RuleRequest): Promise<TaskDetail> {
    const fingerprint = JSON.stringify(body, Object.keys(body).sort());
    if (fingerprint !== this.fingerprint || this.completed) {
      this.fingerprint = fingerprint; this.key = crypto.randomUUID(); this.completed = false;
    }
    const result = await tasksApi.create(body, this.key);
    this.completed = true;
    return result;
  }
}
