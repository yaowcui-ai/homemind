import type {
  ControlInput, ControlResult, EntityInput, EntityPatch, EntityView, FaultMode,
  RoomPatch, RoomView, SensorEvent, Snapshot,
} from './simulation.types';

class SimulationError extends Error {}
const invalidData = '服务返回了无法识别的家庭数据。';
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const maybeNumber = (v: unknown) => v === null || number(v);
const maybeBoolean = (v: unknown) => v === null || typeof v === 'boolean';
const maybeText = (v: unknown) => v === null || text(v);
const types = ['light', 'climate', 'cover', 'temperature', 'occupancy', 'window'];
const faults = ['none', 'offline', 'fail_before', 'response_lost', 'no_effect', 'delayed'];

function isRoom(v: unknown): v is RoomView {
  return object(v) && text(v.id) && text(v.name)
    && maybeText(v.primary_temperature_entity_id) && maybeText(v.primary_occupancy_entity_id)
    && maybeNumber(v.temperature_c) && maybeBoolean(v.occupied) && maybeBoolean(v.window_open);
}

function isEntity(v: unknown): v is EntityView {
  return object(v) && text(v.id) && text(v.room_id) && text(v.name)
    && typeof v.type === 'string' && types.includes(v.type)
    && typeof v.enabled === 'boolean' && typeof v.available === 'boolean' && typeof v.known === 'boolean'
    && object(v.state) && Object.values(v.state).every((s) => s === null || number(s) || typeof s === 'boolean' || typeof s === 'string')
    && object(v.config) && Object.values(v.config).every((s) => number(s) || typeof s === 'boolean' || typeof s === 'string')
    && number(v.version) && number(v.observed_at_minutes) && number(v.energy_wh)
    && object(v.fault) && typeof v.fault.mode === 'string' && faults.includes(v.fault.mode)
    && number(v.fault.delay_minutes) && maybeNumber(v.pending_until_minutes);
}

function isSnapshot(v: unknown): v is Snapshot {
  return object(v) && text(v.home_id) && text(v.world_id)
    && number(v.revision) && number(v.config_revision) && number(v.simulated_minutes)
    && text(v.model_version) && number(v.outdoor_temperature_c) && number(v.energy_wh)
    && Array.isArray(v.rooms) && v.rooms.every(isRoom)
    && Array.isArray(v.entities) && v.entities.every(isEntity)
    && number(v.archived_count) && Array.isArray(v.recent_events)
    && v.recent_events.every((e) => object(e) && number(e.sequence) && number(e.at_minutes)
      && text(e.kind) && text(e.message) && maybeText(e.entity_id));
}

async function request(path: string, method = 'GET', body?: unknown): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api/simulation${path}`, {
      method, signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let data: unknown;
    try { data = await response.json(); } catch { throw new SimulationError(invalidData); }
    if (!response.ok) {
      if (object(data) && object(data.detail) && text(data.detail.message)) {
        throw new SimulationError(data.detail.message.slice(0, 240));
      }
      throw new SimulationError(response.status === 422 ? '参数不符合要求，请检查输入。' : '操作未完成，请刷新家庭状态后重试。');
    }
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new SimulationError('操作请求超时，请先刷新状态，确认是否已生效。');
    if (error instanceof SimulationError) throw error;
    throw new SimulationError('无法连接仿真服务，请检查后端并重试。');
  } finally { clearTimeout(timer); }
}

async function snapshot(path: string, method = 'GET', body?: unknown): Promise<Snapshot> {
  const data = await request(path, method, body);
  if (!isSnapshot(data)) throw new SimulationError(invalidData);
  return data;
}

export const simulationApi = {
  getSnapshot: () => snapshot(''),
  addRoom: (name: string, initial_temperature_c = 27) => snapshot('/rooms', 'POST', { name, initial_temperature_c }),
  updateRoom: (id: string, patch: RoomPatch) => snapshot(`/rooms/${encodeURIComponent(id)}`, 'PATCH', patch),
  removeRoom: (id: string) => snapshot(`/rooms/${encodeURIComponent(id)}`, 'DELETE'),
  addEntity: (input: EntityInput) => snapshot('/entities', 'POST', input),
  updateEntity: (id: string, patch: EntityPatch) => snapshot(`/entities/${encodeURIComponent(id)}`, 'PATCH', patch),
  removeEntity: (id: string) => snapshot(`/entities/${encodeURIComponent(id)}`, 'DELETE'),
  event: (input: SensorEvent) => snapshot('/events', 'POST', input),
  setFault: (id: string, mode: FaultMode, delay_minutes = 2) => snapshot(`/faults/${encodeURIComponent(id)}`, 'POST', { mode, delay_minutes }),
  advance: (minutes: number) => snapshot('/advance', 'POST', { minutes }),
  reset: () => snapshot('/reset', 'POST', {}),
  async control(id: string, input: ControlInput): Promise<ControlResult> {
    const data = await request(`/controls/${encodeURIComponent(id)}`, 'POST', input);
    if (!object(data) || !['verified', 'failed', 'unknown'].includes(String(data.outcome))
      || !text(data.message) || !text(data.entity_id) || !text(data.world_id) || !number(data.revision)) {
      throw new SimulationError(invalidData);
    }
    return data as unknown as ControlResult;
  },
};
