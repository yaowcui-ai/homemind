import type { Snapshot } from '../../api/simulation.types';
import type { AgentOption, PlannedAction } from '../../api/tasks.types';

export function roomLabel(snapshot: Snapshot, id: string) {
  const room = snapshot.rooms.find((r) => r.id === id);
  if (!room) return `未找到房间（${id.slice(-6)}）`;
  if (snapshot.rooms.filter((r) => r.name === room.name).length < 2) return room.name;
  const temperature = room.temperature_c === null ? '温度未知' : `${room.temperature_c}℃`;
  const count = snapshot.entities.filter((e) => e.room_id === id && e.enabled).length;
  const same = snapshot.rooms.filter((r) => r.name === room.name && r.temperature_c === room.temperature_c
    && snapshot.entities.filter((e) => e.room_id === r.id && e.enabled).length === count).length > 1;
  return `${room.name} · ${temperature} · ${count} 个设备${same ? ` · ${id.slice(-6)}` : ''}`;
}
export function entityLabel(snapshot: Snapshot, id: string) {
  const entity = snapshot.entities.find((e) => e.id === id);
  if (!entity) return `未找到设备（${id.slice(-6)}）`;
  const same = snapshot.entities.filter((e) => e.room_id === entity.room_id && e.name === entity.name).length > 1;
  return `${roomLabel(snapshot, entity.room_id)} · ${entity.name}${same ? ` · ${id.slice(-6)}` : ''}`;
}
export function optionLabel(snapshot: Snapshot, option: AgentOption) {
  return option.kind === 'room' ? roomLabel(snapshot, option.id) : entityLabel(snapshot, option.id);
}
export function actionTarget(action: PlannedAction) {
  const p = action.parameters;
  if (action.action === 'set_light') return [p.brightness_pct !== undefined ? Number(p.brightness_pct) > 0 ? '打开灯光' : '关闭灯光'
    : p.power === false ? '关闭灯光' : p.power === true ? '打开灯光' : null,
    p.brightness_pct === undefined ? null : `亮度 ${p.brightness_pct}%`].filter(Boolean).join(' · ') || '调整灯光设置';
  if (action.action === 'set_climate') return [p.mode === 'off' ? '关闭空调' : p.mode === 'cool' ? '开启制冷' : null,
    p.target_temperature_c === undefined ? null : `目标温度 ${p.target_temperature_c}℃`,
    p.fan_mode === 'low' ? '低速风' : p.fan_mode === 'auto' ? '自动风速' : null].filter(Boolean).join(' · ') || '调整空调设置';
  if (action.action === 'set_cover') return p.position_pct === undefined ? '调整窗帘设置' : `设置窗帘开度 ${p.position_pct}%`;
  return '设置设备目标';
}
