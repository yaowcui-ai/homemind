import { apiRequest, isObject, isText } from './client';
import { parseDetail, parseSummary } from './tasks.validation';
import { isAgentStrategy } from './forecast.validation';
import type { AdvanceRequest, AgentConfig, AgentRequest, ConfirmRequest, ReplyRequest, RuleRequest, TaskDetail, TaskSummary } from './tasks.types';

async function detail(path: string, method = 'GET', body?: unknown, headers?: Record<string, string>, timeoutMs?: number): Promise<TaskDetail> {
  return parseDetail(await apiRequest(path, method, body, headers, timeoutMs));
}
export const tasksApi = {
  async list(submissionKey?: string): Promise<TaskSummary[]> {
    const data = await apiRequest(`/tasks${submissionKey ? `?submission_key=${encodeURIComponent(submissionKey)}` : ''}`);
    if (!Array.isArray(data)) throw new Error('服务返回了无法识别的任务列表。');
    return data.map(parseSummary);
  },
  async agentConfig(): Promise<AgentConfig> {
    const data = await apiRequest('/tasks/agent/config');
    if (!isObject(data) || typeof data.available !== 'boolean' || !isText(data.model)
      || !(data.reason === null || typeof data.reason === 'string')
      || (data.strategies !== undefined && (!Array.isArray(data.strategies) || data.strategies.length > 2
        || !data.strategies.every(isAgentStrategy) || new Set(data.strategies).size !== data.strategies.length))) throw new Error('服务返回了无法识别的模型配置。');
    return data as unknown as AgentConfig;
  },
  get: (id: string) => detail(`/tasks/${encodeURIComponent(id)}`),
  verify: (id: string) => detail(`/tasks/${encodeURIComponent(id)}/verify`, 'POST', {}),
  advance: (id: string, body: AdvanceRequest, key: string) => detail(`/tasks/${encodeURIComponent(id)}/advance`, 'POST', body, { 'Idempotency-Key': key }),
  create: (body: RuleRequest, key: string) => detail('/tasks', 'POST', body, { 'Idempotency-Key': key }),
  createAgent: (body: AgentRequest, key: string) => detail('/tasks/agent', 'POST', body, { 'Idempotency-Key': key }, 80000),
  reply: (id: string, body: ReplyRequest, key: string) => detail(`/tasks/${encodeURIComponent(id)}/reply`, 'POST', body, { 'Idempotency-Key': key }, 80000),
  confirm: (id: string, body: ConfirmRequest, key: string) => detail(`/tasks/${encodeURIComponent(id)}/confirm`, 'POST', body, { 'Idempotency-Key': key }),
};

export { TaskSubmission } from './taskSubmission';
