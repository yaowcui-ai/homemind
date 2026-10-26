import type { EntityType, EntityView, Snapshot } from '../api/simulation.types';

export function makeEntity(type: EntityType = 'light', patch: Partial<EntityView> = {}): EntityView {
  const states = {
    light: { power: false, brightness_pct: 0 },
    climate: { mode: 'off', target_temperature_c: 26, fan_mode: 'auto', hvac_action: 'off' },
    cover: { position_pct: 100 }, temperature: { temperature_c: 28 },
    occupancy: { occupied: false }, window: { window_open: false },
  };
  return {
    id: 'entity-1', room_id: 'room-1', name: '测试实体', type,
    enabled: true, available: true, known: true, state: states[type], config: {},
    version: 1, observed_at_minutes: 0, energy_wh: 0,
    fault: { mode: 'none', delay_minutes: 2 }, pending_until_minutes: null, ...patch,
  };
}

export function makeSnapshot(): Snapshot {
  return {
    home_id: 'demo-home', world_id: 'world-test', revision: 0, config_revision: 0,
    simulated_minutes: 0, model_version: 'thermal-v1', outdoor_temperature_c: 32,
    energy_wh: 0, rooms: [], entities: [], archived_count: 0, recent_events: [],
  };
}
