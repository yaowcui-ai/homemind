import type { Preferences } from './auth.types';
import type { Snapshot } from './simulation.types';

export type Scenario = 'homecoming' | 'sleep' | 'away';
export type TaskScenario = Scenario | 'local';
export type TaskMode = 'rule' | 'single_agent';
export interface RuleRequest {
  scenario: Scenario; room_ids: string[]; target_temperature_c?: number;
  ready_in_minutes?: number; keep_entity_ids?: string[]; protected_room_ids?: string[];
  expected_world_id?: string;
}
export interface AgentRequest {
  text: string; expected_world_id: string; keep_entity_ids?: string[]; protected_room_ids?: string[];
}
export interface ReplyRequest { text: string; expected_turn: number }
export interface ConfirmRequest { expected_turn: number }
export interface AdvanceRequest { expected_world_id: string; expected_simulated_minutes: number }
export interface AdvanceRecord { key: string; request: AdvanceRequest; advanced_to_minutes: number }
export interface AgentConfig { available: boolean; model: string; reason: string | null }
export type TaskStatus = 'queued' | 'planning' | 'running' | 'waiting_input' | 'waiting_confirmation' | 'waiting_verification' | 'succeeded' | 'partial' | 'failed' | 'cancelled';
export interface TaskSummary {
  id: string; mode: TaskMode; scenario: TaskScenario; status: TaskStatus; created_at: number;
  updated_at: number; world_id: string; message: string;
}
export interface PlannedAction {
  entity_id: string; entity_name: string; room_name: string; action: string;
  parameters: Record<string, string | number | boolean>;
}
export interface ActionView extends PlannedAction {
  id: string; status: 'planned' | 'submitted' | 'verified' | 'failed' | 'unknown' | 'skipped';
  transport_outcome: string | null; message: string;
}
export interface Condition { label: string; outcome: 'verified' | 'failed' | 'unknown' | 'pending'; message: string }
export interface TaskPlan {
  actions: PlannedAction[]; constraints: Condition[];
  temperatures: { room_id: string; room_name: string; target: number }[];
  due_at_minutes: number | null;
}
export interface Verification {
  due_at_minutes: number | null; checked_at_minutes: number; conditions: Condition[];
}
export interface AgentOption { id: string; label: string; kind: 'room' | 'entity' }
export interface ProposedPlan {
  kind: 'plan'; scenario: TaskScenario; room_ids: string[]; keep_entity_ids: string[]; protected_room_ids: string[];
  actions: { entity_id: string; room_id: string; action: string; parameters: Record<string, string | number | boolean> }[];
  temperatures: { room_id: string; target: number }[]; ready_in_minutes: number | null; rationale: string;
}
export interface AgentRun {
  turn: number; max_replies: number; question: string | null; options: AgentOption[];
  proposed_plan: ProposedPlan | null; rationale: string | null;
  conversation: { role: 'user' | 'assistant'; text: string; options?: AgentOption[] }[];
  records: { stage: string; message: string; elapsed_ms?: number; duration_ms?: number }[];
  model_calls: number; tool_calls: number; usage: { input_tokens: number; output_tokens: number } | null;
  actual_model: string | null; failure_code: string | null;
  rounds: { turn: number; model_calls: number; tool_calls: number; usage: AgentRun['usage']; elapsed_ms: number }[];
  timings: { planning_ms: number; validation_ms: number; execution_ms: number };
}
interface DetailFields extends Omit<TaskSummary, 'mode'> {
  advance_records?: AdvanceRecord[];
  preferences_snapshot: Preferences; initial_snapshot: Snapshot; final_snapshot: Snapshot;
  actions: ActionView[]; verification: Verification; plan: TaskPlan;
}
export type TaskDetail = DetailFields & (
  { mode: 'rule'; request: RuleRequest; agent_run: null } |
  { mode: 'single_agent'; request: AgentRequest; agent_run: AgentRun }
);
