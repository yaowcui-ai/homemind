import type { Preferences } from './auth.types';
import type { Snapshot } from './simulation.types';

export type Scenario = 'homecoming' | 'sleep' | 'away';
export interface RuleRequest {
  scenario: Scenario; room_ids: string[]; target_temperature_c?: number;
  ready_in_minutes?: number; keep_entity_ids?: string[]; protected_room_ids?: string[];
  expected_world_id?: string;
}
export type TaskStatus = 'queued' | 'running' | 'waiting_input' | 'waiting_verification' | 'succeeded' | 'partial' | 'failed' | 'cancelled';
export interface TaskSummary {
  id: string; scenario: Scenario; status: TaskStatus; created_at: number;
  updated_at: number; world_id: string; message: string;
}
export interface ActionView {
  id: string; entity_id: string; entity_name: string; room_name: string; action: string;
  parameters: Record<string, string | number | boolean>;
  status: 'planned' | 'submitted' | 'verified' | 'failed' | 'unknown' | 'skipped';
  transport_outcome: string | null; message: string;
}
export interface Verification {
  due_at_minutes: number | null; checked_at_minutes: number;
  conditions: { label: string; outcome: 'verified' | 'failed' | 'unknown' | 'pending'; message: string }[];
}
export interface TaskDetail extends TaskSummary {
  request: RuleRequest; preferences_snapshot: Preferences;
  initial_snapshot: Snapshot; final_snapshot: Snapshot; actions: ActionView[]; verification: Verification;
}
