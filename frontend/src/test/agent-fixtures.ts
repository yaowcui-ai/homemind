import { makeEntity, makeSnapshot, makeTask } from './simulation-fixtures';
import type { TaskDetail } from '../api/tasks.types';

export function makeAgentTask(patch: Partial<TaskDetail> = {}): TaskDetail {
  const snapshot = { ...makeSnapshot(), rooms: [
    { id: 'room-1', name: '客厅', temperature_c: 28, occupied: false, window_open: false,
      primary_temperature_entity_id: null, primary_occupancy_entity_id: null },
    { id: 'room-2', name: '客厅', temperature_c: 26, occupied: false, window_open: false,
      primary_temperature_entity_id: null, primary_occupancy_entity_id: null },
  ], entities: [makeEntity('light', { name: '主灯' })] };
  const task = makeTask({ mode: 'single_agent', scenario: 'local', status: 'waiting_input',
    request: { text: '准备一下', expected_world_id: 'world-test', keep_entity_ids: [], protected_room_ids: [] },
    initial_snapshot: snapshot, final_snapshot: snapshot,
    plan: { actions: [], constraints: [], temperatures: [], due_at_minutes: null },
    agent_run: { turn: 0, max_replies: 3, question: '操作哪个客厅？',
      options: [{ id: 'room-1', kind: 'room', label: '客厅' }, { id: 'room-2', kind: 'room', label: '客厅' }],
      proposed_plan: null, rationale: null, conversation: [{ role: 'user', text: '准备一下' }],
      records: [], model_calls: 1, tool_calls: 1, usage: null, actual_model: null, failure_code: null,
      rounds: [], timings: { planning_ms: 10, validation_ms: 1, execution_ms: 0 } },
    verification: { due_at_minutes: null, checked_at_minutes: 0, conditions: [] } });
  return { ...task, ...patch } as TaskDetail;
}
