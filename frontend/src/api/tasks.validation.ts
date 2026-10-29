import { isObject, isNumber, isText } from './client';
import { isPreferences } from './preferences';
import { isSnapshot } from './simulation';
import type { AgentRequest, AgentRun, TaskDetail, TaskSummary } from './tasks.types';
import type { Snapshot } from './simulation.types';
import { forecastContext, forecastRun, isAgentStrategy } from './forecast.validation';

const scenarios = ['homecoming', 'sleep', 'away', 'local'];
const statuses = ['queued', 'planning', 'running', 'waiting_input', 'waiting_confirmation', 'waiting_verification', 'succeeded', 'partial', 'failed', 'cancelled'];
const textArray = (v: unknown) => Array.isArray(v) && v.every(isText);
const nullableText = (v: unknown) => v === null || typeof v === 'string';
const nullableNumber = (v: unknown) => v === null || isNumber(v);
const parameters = (v: unknown) => isObject(v) && Object.values(v).every((p) => typeof p === 'string' || typeof p === 'boolean' || isNumber(p));
const action = (v: unknown) => isObject(v) && isText(v.entity_id) && isText(v.entity_name) && isText(v.room_name) && isText(v.action) && parameters(v.parameters);
const condition = (v: unknown) => isObject(v) && isText(v.label) && typeof v.message === 'string' && ['verified', 'failed', 'unknown', 'pending'].includes(String(v.outcome));
const option = (v: unknown) => isObject(v) && isText(v.id) && isText(v.label) && ['room', 'entity'].includes(String(v.kind));
const usage = (v: unknown) => v === null || (isObject(v) && isNumber(v.input_tokens) && isNumber(v.output_tokens));
const temperature = (v: unknown) => isObject(v) && isText(v.room_id) && isNumber(v.target);
function plan(v: unknown) {
  return isObject(v) && Array.isArray(v.actions) && v.actions.every(action) && Array.isArray(v.constraints) && v.constraints.every(condition)
    && Array.isArray(v.temperatures) && v.temperatures.every((t) => temperature(t) && isObject(t) && isText(t.room_name)) && nullableNumber(v.due_at_minutes);
}
function proposedPlan(v: unknown) {
  return v === null || (isObject(v) && v.kind === 'plan' && scenarios.includes(String(v.scenario)) && textArray(v.room_ids)
    && textArray(v.keep_entity_ids) && textArray(v.protected_room_ids) && Array.isArray(v.actions)
    && v.actions.every((a) => isObject(a) && isText(a.entity_id) && isText(a.room_id) && isText(a.action) && parameters(a.parameters))
    && Array.isArray(v.temperatures) && v.temperatures.every(temperature) && nullableNumber(v.ready_in_minutes) && typeof v.rationale === 'string');
}
function diagnostic(v: unknown) {
  return v === undefined || v === null || (isObject(v) && v.phase === 'validation'
    && ['plan', 'clarify'].includes(String(v.output_kind)) && isText(v.code)
    && typeof v.field_path === 'string'
    && /^\$\.(?:options\[\d+\]\.id|(?:room_ids|keep_entity_ids|protected_room_ids)(?:\[\d+\])?|actions\[\d+\]\.(?:entity_id|room_id|action|parameters)|temperatures(?:\[\d+\]\.(?:room_id|target))?|ready_in_minutes)$/.test(v.field_path)
    && (v.reference_kind === null || ['room', 'entity'].includes(String(v.reference_kind)))
    && (v.reference_in_current_home === null || typeof v.reference_in_current_home === 'boolean'));
}
function agentRun(v: unknown): v is AgentRun {
  return isObject(v) && forecastRun(v) && isNumber(v.turn) && isNumber(v.max_replies) && nullableText(v.question)
    && Array.isArray(v.options) && v.options.every(option) && proposedPlan(v.proposed_plan) && nullableText(v.rationale)
    && Array.isArray(v.conversation) && v.conversation.every((c) => isObject(c) && ['user', 'assistant'].includes(String(c.role))
      && typeof c.text === 'string' && (c.options === undefined || (Array.isArray(c.options) && c.options.every(option))))
    && Array.isArray(v.records) && v.records.every((r) => isObject(r) && isText(r.stage) && typeof r.message === 'string'
      && (r.elapsed_ms === undefined || isNumber(r.elapsed_ms)) && (r.duration_ms === undefined || isNumber(r.duration_ms)))
    && isNumber(v.model_calls) && isNumber(v.tool_calls) && usage(v.usage) && (v.actual_model === undefined || nullableText(v.actual_model)) && nullableText(v.failure_code) && diagnostic(v.diagnostic)
    && Array.isArray(v.rounds) && v.rounds.every((r) => isObject(r) && isNumber(r.turn) && isNumber(r.model_calls) && isNumber(r.tool_calls) && usage(r.usage) && isNumber(r.elapsed_ms))
    && isObject(v.timings) && ['planning_ms', 'validation_ms', 'execution_ms'].every((key) => isNumber((v.timings as Record<string, unknown>)[key]));
}

export function parseSummary(v: unknown): TaskSummary {
  if (!isObject(v) || !isText(v.id) || !scenarios.includes(String(v.scenario)) || !statuses.includes(String(v.status))
    || !isNumber(v.created_at) || !isNumber(v.updated_at) || !isText(v.world_id) || typeof v.message !== 'string'
    || (v.mode !== undefined && !['rule', 'single_agent', 'multi_agent'].includes(String(v.mode)))) throw new Error('服务返回了无法识别的任务信息。');
  return { ...v, mode: v.mode ?? 'rule' } as TaskSummary;
}

export function parseDetail(data: unknown): TaskDetail {
  const summary = parseSummary(data);
  if (!isObject(data)) throw new Error('服务返回了无法识别的任务信息。');
  const v = data;
  const request = v.request;
  const legacy = v.mode === undefined;
  const validRequest = isObject(request) && (summary.mode !== 'rule'
    ? isText(request.text) && isText(request.expected_world_id) && (request.strategy === undefined || isAgentStrategy(request.strategy))
    : ['homecoming', 'sleep', 'away'].includes(String(request.scenario)) && textArray(request.room_ids))
    && (request.keep_entity_ids === undefined || textArray(request.keep_entity_ids))
    && (request.protected_room_ids === undefined || textArray(request.protected_room_ids));
  if (!validRequest || !isPreferences(v.preferences_snapshot) || !isSnapshot(v.initial_snapshot) || !isSnapshot(v.final_snapshot)
    || (v.advance_records !== undefined && (!Array.isArray(v.advance_records) || !v.advance_records.every((r) => isObject(r)
      && isText(r.key) && isObject(r.request) && isText(r.request.expected_world_id)
      && Number.isSafeInteger(r.request.expected_simulated_minutes) && Number(r.request.expected_simulated_minutes) >= 0
      && Number.isSafeInteger(r.advanced_to_minutes) && Number(r.advanced_to_minutes) >= 0)))
    || !Array.isArray(v.actions) || !v.actions.every((a) => action(a) && isObject(a) && isText(a.id)
      && ['planned', 'submitted', 'verified', 'failed', 'unknown', 'skipped'].includes(String(a.status)) && nullableText(a.transport_outcome) && typeof a.message === 'string')
    || !isObject(v.verification) || !nullableNumber(v.verification.due_at_minutes) || !isNumber(v.verification.checked_at_minutes)
    || !Array.isArray(v.verification.conditions) || !v.verification.conditions.every(condition)
    || (!(legacy && v.plan === undefined) && !plan(v.plan))
    || (summary.mode !== 'rule' ? !agentRun(v.agent_run) : !(v.agent_run === null || (legacy && v.agent_run === undefined)))) {
    throw new Error('服务返回了无法识别的任务信息。');
  }
  const run = v.agent_run as AgentRun | null | undefined;
  if (summary.mode === 'multi_agent' && ['succeeded', 'partial', 'waiting_verification'].includes(summary.status)
    && (!Array.isArray(v.actions) || !v.actions.length)) throw new Error('服务返回了无法识别的任务信息。');
  if (summary.mode !== 'rule' && run && !forecastContext(run, request as unknown as AgentRequest,
    v.initial_snapshot as unknown as Snapshot, summary.status, summary.mode)) throw new Error('服务返回了无法识别的任务信息。');
  return { ...v, ...summary, plan: v.plan ?? { actions: [], constraints: [], temperatures: [], due_at_minutes: null },
    agent_run: run ? { ...run, actual_model: run.actual_model ?? null } : null } as TaskDetail;
}
