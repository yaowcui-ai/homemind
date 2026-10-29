import { isObject, isNumber, isText } from './client';
import type { AgentRun, AgentRequest, AgentStrategy } from './tasks.types';
import type { Snapshot } from './simulation.types';
import { expertContext, expertRunShape } from './roles.validation';

export const isAgentStrategy = (v: unknown): v is AgentStrategy => v === 'standard' || v === 'single_forecast' || v === 'expert_forecast';
const integer = (v: unknown, min: number, max: number) => Number.isSafeInteger(v) && Number(v) >= min && Number(v) <= max;
const ids = (v: unknown, max: number) => Array.isArray(v) && v.length <= max && v.every(isText) && new Set(v).size === v.length;
const nonnegative = (v: unknown) => isNumber(v) && v >= 0;

/** Validate the optional extension before any forecast values reach the UI. */
export function forecastRun(v: Record<string, unknown>): boolean {
  const extension = ['strategy', 'pipeline_version', 'goal', 'forecast', 'selected_candidate_id', 'preference_optimal'];
  if (!extension.some((key) => v[key] !== undefined)) return true;
  const expert = v.strategy === 'expert_forecast';
  if ((!expert && v.strategy !== 'single_forecast') || v.pipeline_version !== (expert ? 'd3-experts-v1' : 'd2-forecast-v1')
    || !(v.selected_candidate_id === null || isText(v.selected_candidate_id))
    || !(v.preference_optimal === null || typeof v.preference_optimal === 'boolean')) return false;
  if (expert && !expertRunShape(v)) return false;
  const g = v.goal;
  if (g !== null && (!isObject(g) || g.kind !== 'goal' || !isText(g.room_id) || !isText(g.climate_entity_id)
    || !(g.cover_entity_id === null || isText(g.cover_entity_id))
    || !integer(g.target_temperature_c, 16, 30) || !integer(g.ready_in_minutes, 1, 1440)
    || !['comfort_first', 'energy_first'].includes(String(g.priority))
    || !Array.isArray(g.allowed_fan_modes) || !g.allowed_fan_modes.length || g.allowed_fan_modes.length > 2
    || !g.allowed_fan_modes.every((f) => f === 'low' || f === 'auto') || new Set(g.allowed_fan_modes).size !== g.allowed_fan_modes.length
    || !['allow_open_close', 'keep'].includes(String(g.cover_constraint)) || !ids(g.keep_entity_ids, 1000) || !ids(g.protected_room_ids, 100))) return false;
  const f = v.forecast;
  if (f === null) return v.selected_candidate_id === null && v.preference_optimal === null;
  if (!isObject(g) || !isObject(f) || !isText(f.model_version) || !isObject(f.source)
    || !isText(f.source.world_id) || ![f.source.revision, f.source.config_revision, f.source.simulated_minutes].every((n) => integer(n, 0, Number.MAX_SAFE_INTEGER))
    || !ids(f.energy_scope_entity_ids, 2) || !(f.energy_scope_entity_ids as unknown[]).length
    || !Array.isArray(f.candidates) || f.candidates.length < 1 || f.candidates.length > 4) return false;
  const candidates = f.candidates;
  if (!candidates.every((c) => isObject(c) && isText(c.id) && ['low', 'auto'].includes(String(c.fan_mode))
    && (g.allowed_fan_modes as unknown[]).includes(c.fan_mode)
    && (c.cover_position_pct === null || integer(c.cover_position_pct, 0, 100))
    && isNumber(c.end_temperature_c) && c.end_temperature_c >= 0 && c.end_temperature_c <= 50
    && (c.first_observed_goal_minute === null || integer(c.first_observed_goal_minute, 0, Number(g.ready_in_minutes)))
    && typeof c.deadline_met === 'boolean' && c.deadline_met === (Number(c.end_temperature_c) <= Number(g.target_temperature_c))
    && (!c.deadline_met || c.first_observed_goal_minute !== null) && nonnegative(c.energy_wh)
    && Array.isArray(c.actions) && c.actions.length >= 1 && c.actions.length <= 2
    && c.actions.every((a) => isObject(a) && isText(a.entity_id) && a.room_id === g.room_id
      && ['set_climate', 'set_cover'].includes(String(a.action)) && isObject(a.parameters)
      && Object.values(a.parameters).every((p) => typeof p === 'string' || typeof p === 'boolean' || isNumber(p))))) return false;
  const scope = [g.climate_entity_id, ...(g.cover_entity_id ? [g.cover_entity_id] : [])];
  if (!(f.energy_scope_entity_ids as unknown[]).every((id) => scope.includes(id))
    || (f.energy_scope_entity_ids as unknown[]).length !== scope.length) return false;
  for (const c of candidates) {
    const ac = c.actions.filter((a: Record<string, unknown>) => a.action === 'set_climate');
    const covers = c.actions.filter((a: Record<string, unknown>) => a.action === 'set_cover');
    if (ac.length !== 1 || ac[0].entity_id !== g.climate_entity_id || Object.keys(ac[0].parameters).length !== 3
      || ac[0].parameters.mode !== 'cool' || ac[0].parameters.target_temperature_c !== g.target_temperature_c
      || ac[0].parameters.fan_mode !== c.fan_mode) return false;
    const moving = g.cover_entity_id !== null && g.cover_constraint === 'allow_open_close';
    if (moving ? covers.length !== 1 || covers[0].entity_id !== g.cover_entity_id
      || ![0, 100].includes(c.cover_position_pct) || Object.keys(covers[0].parameters).length !== 1
      || covers[0].parameters.position_pct !== c.cover_position_pct : covers.length !== 0) return false;
    if (g.cover_entity_id === null && c.cover_position_pct !== null) return false;
  }
  return new Set(candidates.map((c) => c.id)).size === candidates.length
    && (v.selected_candidate_id === null || candidates.some((c) => c.id === v.selected_candidate_id));
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((id) => b.includes(id));
const canonical = (v: unknown): string => JSON.stringify(v, (_key, value) => isObject(value)
  ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]])) : value);
const sameActions = (a: { entity_id: string; room_id: string; action: string; parameters: unknown }[], b: { entity_id: string; room_id: string; action: string; parameters: unknown }[]) =>
  canonical([...a].sort((a, b) => a.entity_id.localeCompare(b.entity_id)))
  === canonical([...b].sort((a, b) => a.entity_id.localeCompare(b.entity_id)));

/** Public evidence must belong to this task's original round, not a different home/version. */
export function forecastContext(run: AgentRun, request: AgentRequest, snapshot: Snapshot, status: string, mode: 'single_agent' | 'multi_agent'): boolean {
  const experimental = request.strategy === 'single_forecast' || request.strategy === 'expert_forecast';
  if (experimental ? request.strategy !== run.strategy : run.strategy !== undefined) return false;
  if ((mode === 'multi_agent') !== (run.strategy === 'expert_forecast')) return false;
  if (run.strategy === 'expert_forecast' && !expertContext(run, status)) return false;
  if (!experimental) return true;
  const goal = run.goal; const f = run.forecast;
  if (goal) {
    if (!snapshot.rooms.some((r) => r.id === goal.room_id)
      || !snapshot.entities.some((e) => e.id === goal.climate_entity_id && e.type === 'climate' && e.room_id === goal.room_id)
      || (goal.cover_entity_id !== null && !snapshot.entities.some((e) => e.id === goal.cover_entity_id && e.type === 'cover' && e.room_id === goal.room_id))
      || !goal.keep_entity_ids.every((id) => snapshot.entities.some((e) => e.id === id))
      || !goal.protected_room_ids.every((id) => snapshot.rooms.some((r) => r.id === id))
      || !(request.keep_entity_ids ?? []).every((id) => goal.keep_entity_ids.includes(id))
      || !(request.protected_room_ids ?? []).every((id) => goal.protected_room_ids.includes(id))) return false;
  }
  if (f && (!goal || f.model_version !== snapshot.model_version
    || f.source.world_id !== snapshot.world_id || f.source.revision !== snapshot.revision
    || f.source.config_revision !== snapshot.config_revision || f.source.simulated_minutes !== snapshot.simulated_minutes)) return false;
  if (f && goal?.cover_entity_id && goal.cover_constraint === 'keep') {
    const position = snapshot.entities.find((e) => e.id === goal.cover_entity_id)?.state.position_pct;
    if (f.candidates.some((c) => c.cover_position_pct !== position)) return false;
  }
  const selected = f?.candidates.find((c) => c.id === run.selected_candidate_id);
  if (status === 'waiting_confirmation' && (!goal || !selected || !selected.deadline_met || !run.proposed_plan)) return false;
  if (selected) {
    const p = run.proposed_plan;
    if (!goal || !p || typeof run.preference_optimal !== 'boolean' || p.scenario !== 'homecoming'
      || !sameSet(p.room_ids, [goal.room_id]) || !sameSet(p.keep_entity_ids, goal.keep_entity_ids)
      || !sameSet(p.protected_room_ids, goal.protected_room_ids) || p.ready_in_minutes !== goal.ready_in_minutes
      || p.temperatures.length !== 1 || p.temperatures[0].room_id !== goal.room_id || p.temperatures[0].target !== goal.target_temperature_c
      || !sameActions(p.actions, selected.actions)) return false;
  }
  return true;
}
