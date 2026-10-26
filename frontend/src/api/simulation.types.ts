export type EntityType = 'light' | 'climate' | 'cover' | 'temperature' | 'occupancy' | 'window';
export type FaultMode = 'none' | 'offline' | 'fail_before' | 'response_lost' | 'no_effect' | 'delayed';
export type StateValue = string | number | boolean | null;

export interface RoomView {
  id: string;
  name: string;
  primary_temperature_entity_id: string | null;
  primary_occupancy_entity_id: string | null;
  temperature_c: number | null;
  occupied: boolean | null;
  window_open: boolean | null;
}

export interface EntityView {
  id: string;
  room_id: string;
  name: string;
  type: EntityType;
  enabled: boolean;
  available: boolean;
  known: boolean;
  state: Record<string, StateValue>;
  config: Record<string, string | number | boolean>;
  version: number;
  observed_at_minutes: number;
  energy_wh: number;
  fault: { mode: FaultMode; delay_minutes: number };
  pending_until_minutes: number | null;
}

export interface SimulationEvent {
  sequence: number;
  at_minutes: number;
  kind: string;
  message: string;
  entity_id: string | null;
}

export interface Snapshot {
  home_id: string;
  world_id: string;
  revision: number;
  config_revision: number;
  simulated_minutes: number;
  model_version: string;
  outdoor_temperature_c: number;
  energy_wh: number;
  rooms: RoomView[];
  entities: EntityView[];
  archived_count: number;
  recent_events: SimulationEvent[];
}

export interface ControlResult {
  outcome: 'verified' | 'failed' | 'unknown';
  message: string;
  entity_id: string;
  world_id: string;
  revision: number;
}

export interface EntityInput {
  room_id: string;
  name: string;
  type: EntityType;
  config?: Record<string, string | number | boolean>;
}

export interface RoomPatch {
  name?: string;
  primary_temperature_entity_id?: string | null;
  primary_occupancy_entity_id?: string | null;
}

export interface EntityPatch {
  name?: string;
  room_id?: string;
  enabled?: boolean;
  config?: Record<string, string | number | boolean>;
}

export interface SensorEvent {
  entity_id: string;
  temperature_c?: number;
  occupied?: boolean;
  window_open?: boolean;
  available?: boolean;
  known?: boolean;
}

export interface ControlInput {
  action: 'set_light' | 'set_climate' | 'set_cover';
  parameters: Record<string, string | number | boolean>;
  expected_world_id?: string;
}
