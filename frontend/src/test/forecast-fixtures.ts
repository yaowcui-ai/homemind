import { makeAgentTask } from './agent-fixtures';
import type { ForecastGoal, TaskDetail } from '../api/tasks.types';
import { makeEntity } from './simulation-fixtures';

export function makeForecastTask() {
  const task = makeAgentTask({ status: 'waiting_confirmation', scenario: 'homecoming' });
  if (task.mode !== 'single_agent') throw new Error('Expected an agent fixture');
  const snapshot = { ...task.initial_snapshot, model_version: 'm2-decimal-minute-v1',
    entities: [makeEntity('climate', { id: 'climate-1', name: '客厅空调' })] };
  const actions = (fan: 'low' | 'auto') => [{ entity_id: 'climate-1', room_id: 'room-1', action: 'set_climate',
    parameters: { mode: 'cool', target_temperature_c: 26, fan_mode: fan } }];
  const goal: ForecastGoal = { kind: 'goal', room_id: 'room-1', climate_entity_id: 'climate-1', cover_entity_id: null,
    target_temperature_c: 26, ready_in_minutes: 60, priority: 'energy_first',
    allowed_fan_modes: ['low', 'auto'], cover_constraint: 'keep', keep_entity_ids: [], protected_room_ids: [] };
  const proposed = { kind: 'plan' as const, scenario: 'homecoming' as const, room_ids: ['room-1'], keep_entity_ids: [], protected_room_ids: [],
    actions: actions('low'), temperatures: [{ room_id: 'room-1', target: 26 }], ready_in_minutes: 60, rationale: '按冻结候选选择低风' };
  return { ...task, initial_snapshot: snapshot, final_snapshot: snapshot,
    plan: { actions: actions('low').map((a) => ({ ...a, entity_name: '客厅空调', room_name: '客厅' })),
      constraints: [], temperatures: [{ room_id: 'room-1', room_name: '客厅', target: 26 }], due_at_minutes: 60 },
    request: { ...task.request, strategy: 'single_forecast' as const }, agent_run: {
    ...task.agent_run, strategy: 'single_forecast' as const, pipeline_version: 'd2-forecast-v1', goal,
    question: null, options: [], proposed_plan: proposed, selected_candidate_id: 'c1', preference_optimal: true as boolean,
    forecast: { model_version: 'm2-decimal-minute-v1', source: { world_id: 'world-test', revision: 0,
      config_revision: 0, simulated_minutes: 0 }, energy_scope_entity_ids: ['climate-1'], candidates: [
      { id: 'c1', fan_mode: 'low', cover_position_pct: null, end_temperature_c: 26,
        first_observed_goal_minute: 41, deadline_met: true, energy_wh: 550.05, actions: actions('low') },
      { id: 'c2', fan_mode: 'auto', cover_position_pct: null, end_temperature_c: 26,
        first_observed_goal_minute: 17, deadline_met: true, energy_wh: 850.05, actions: actions('auto') },
    ] },
  } } satisfies TaskDetail;
}
