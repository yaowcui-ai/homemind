import { isNumber, isObject, isText } from './client';
import type { AgentRun, RoleMetrics } from './tasks.types';

const order = ['coordinator_goal', 'comfort', 'energy', 'coordinator_plan'];
const metricFields = ['role', 'status', 'model_calls', 'tool_calls', 'usage', 'actual_model', 'elapsed_ms', 'failure_code'];
const integer = (v: unknown, min: number, max: number) => Number.isSafeInteger(v) && Number(v) >= min && Number(v) <= max;
const usage = (v: unknown) => v === null || (isObject(v) && integer(v.input_tokens, 0, 1e9) && integer(v.output_tokens, 0, 1e9));
const sameUsage = (a: RoleMetrics['usage'], b: RoleMetrics['usage']) => a === null || b === null
  ? a === b : a.input_tokens === b.input_tokens && a.output_tokens === b.output_tokens;

function metrics(v: unknown): v is RoleMetrics {
  if (!isObject(v) || Object.keys(v).some((key) => !metricFields.includes(key) && key !== 'advice')
    || !order.includes(String(v.role)) || !['succeeded', 'failed', 'cancelled', 'skipped'].includes(String(v.status))
    || !integer(v.model_calls, 0, v.role === 'coordinator_plan' ? 3 : 1) || !integer(v.tool_calls, 0, v.role === 'coordinator_plan' ? 6 : 0)
    || !usage(v.usage) || !(v.actual_model === null || (isText(v.actual_model) && v.actual_model.length <= 200))
    || !isNumber(v.elapsed_ms) || v.elapsed_ms < 0
    || !(v.failure_code === null || (typeof v.failure_code === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(v.failure_code)))) return false;
  if (v.model_calls === 0 && (v.usage !== null || v.actual_model !== null || v.tool_calls !== 0)) return false;
  if (v.status === 'skipped') return v.model_calls === 0 && v.tool_calls === 0 && v.usage === null && v.actual_model === null;
  return v.status === 'succeeded' ? Number(v.model_calls) >= 1 && v.failure_code === null : v.failure_code !== null;
}

function advice(v: unknown, role: string): boolean {
  return isObject(v) && Object.keys(v).every((key) => ['role', 'outcome', 'preferred_candidate_id', 'evidence_refs', 'public_summary'].includes(key))
    && v.role === role && ['recommend', 'clarify', 'refuse'].includes(String(v.outcome))
    && (v.outcome === 'recommend' ? isText(v.preferred_candidate_id) : v.preferred_candidate_id === null)
    && Array.isArray(v.evidence_refs) && v.evidence_refs.length <= 5 && v.evidence_refs.every(isText)
    && new Set(v.evidence_refs).size === v.evidence_refs.length
    && typeof v.public_summary === 'string' && v.public_summary.trim().length > 0 && v.public_summary.length <= 1000;
}

function ordered(v: unknown, withAdvice: boolean): v is RoleMetrics[] {
  return Array.isArray(v) && v.length === 4 && v.every((record, i) => metrics(record) && record.role === order[i]
    && (withAdvice ? (isObject(record) && (record.status === 'succeeded' && ['comfort', 'energy'].includes(record.role)
      ? advice(record.advice, record.role) : record.advice === null)) : !Object.hasOwn(record, 'advice')));
}

function summedUsage(roles: RoleMetrics[]): RoleMetrics['usage'] {
  const issued = roles.filter((r) => r.model_calls > 0);
  if (!issued.length || issued.some((r) => r.usage === null)) return null;
  return issued.reduce((sum, r) => ({ input_tokens: sum.input_tokens + r.usage!.input_tokens,
    output_tokens: sum.output_tokens + r.usage!.output_tokens }), { input_tokens: 0, output_tokens: 0 });
}

/** Counters belong to real completed/cancelled stages, never inferred from a mode name. */
export function expertRunShape(v: Record<string, unknown>): boolean {
  if (!Array.isArray(v.role_runs) || (v.role_runs.length !== 0 && !ordered(v.role_runs, true))
    || !Array.isArray(v.rounds) || v.rounds.length > 4 || !integer(v.turn, 0, 3)
    || !integer(v.model_calls, 0, 12) || !integer(v.tool_calls, 0, 24) || !usage(v.usage)) return false;
  let calls = 0; let tools = 0; const all: RoleMetrics[] = [];
  for (const [index, round] of v.rounds.entries()) {
    if (!isObject(round) || !ordered(round.roles, false) || !integer(round.model_calls, 0, 6)
      || round.turn !== index || index > Number(v.turn)
      || !integer(round.tool_calls, 0, 6) || !usage(round.usage)
      || round.roles.reduce((n, r) => n + r.model_calls, 0) !== round.model_calls
      || round.roles.reduce((n, r) => n + r.tool_calls, 0) !== round.tool_calls
      || !sameUsage(summedUsage(round.roles), round.usage as RoleMetrics['usage'])) return false;
    calls += Number(round.model_calls); tools += Number(round.tool_calls); all.push(...round.roles);
  }
  if (v.rounds.length !== Number(v.turn) && v.rounds.length !== Number(v.turn) + 1) return false;
  if (calls !== v.model_calls || tools !== v.tool_calls || !sameUsage(summedUsage(all), v.usage as RoleMetrics['usage'])) return false;
  if (v.role_runs.length) {
    const last = v.rounds.at(-1);
    if (!isObject(last) || last.turn !== v.turn || !Array.isArray(last.roles)) return false;
    const history = last.roles as RoleMetrics[];
    const keys: (keyof RoleMetrics)[] = ['role', 'status', 'model_calls', 'tool_calls', 'actual_model', 'elapsed_ms', 'failure_code'];
    if (!(v.role_runs as RoleMetrics[]).every((r, i) => keys.every((k) => r[k] === history[i][k]) && sameUsage(r.usage, history[i].usage))) return false;
  }
  return true;
}

export function expertContext(run: AgentRun, status: string): boolean {
  const roles = run.role_runs;
  if (!roles?.length) return ((status === 'planning' && run.failure_code === null)
    || (status === 'failed' && run.failure_code === 'request_cancelled'))
    && run.goal === null && run.forecast === null && run.proposed_plan === null
    && run.selected_candidate_id === null && run.preference_optimal === null;
  const executable = ['waiting_confirmation', 'waiting_verification', 'succeeded', 'partial'].includes(status);
  if (executable && (run.failure_code !== null || !run.selected_candidate_id || roles.some((r) => r.status !== 'succeeded'))) return false;
  if (status === 'waiting_input' && (run.failure_code !== null || roles.some((r) => ['failed', 'cancelled'].includes(r.status)))) return false;
  if (run.failure_code === 'analysis_incomplete' && (status !== 'failed' || run.selected_candidate_id !== null
    || !roles.some((r) => ['comfort', 'energy'].includes(r.role) && r.status !== 'succeeded'))) return false;
  for (const r of roles) {
    const a = r.advice;
    if (!a) continue;
    if (!run.goal || !run.forecast) return false;
    const allowed = ['goal', ...run.forecast.candidates.map((c) => `candidate:${c.id}`)];
    if (a.evidence_refs.some((ref) => !allowed.includes(ref))) return false;
    if (a.outcome === 'recommend' && (!run.forecast.candidates.some((c) => c.id === a.preferred_candidate_id && c.deadline_met)
      || !a.evidence_refs.includes(`candidate:${a.preferred_candidate_id}`))) return false;
    if (executable && a.outcome !== 'recommend') return false;
    if (status === 'waiting_input' && a.outcome === 'refuse') return false;
  }
  return true;
}
