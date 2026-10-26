import type { ControlResult, EntityType, FaultMode, Snapshot } from '../../api/simulation.types';

export const entityLabels: Record<EntityType, string> = {
  light: '灯光', climate: '空调', cover: '电动窗帘',
  temperature: '温度传感器', occupancy: '人体存在传感器', window: '窗户传感器',
};
export const faultLabels: Record<FaultMode, string> = {
  none: '正常', offline: '设备离线', fail_before: '执行前失败',
  response_lost: '执行后响应丢失', no_effect: '指令无效果', delayed: '延迟生效',
};
export const faultDescriptions: Record<FaultMode, string> = {
  none: '清除故障，后续操作正常执行。',
  offline: '无法读取或控制，保留内部环境状态。',
  fail_before: '动作开始前失败，设备不改变。',
  response_lost: '动作已执行但响应未知；独立读取状态核验。',
  no_effect: '指令受理但设备不改变，核验失败。',
  delayed: '动作等待仿真时间到达后生效，不等待现实时间。',
};
export const isSensor = (type: EntityType) => ['temperature', 'occupancy', 'window'].includes(type);
export type Operation = (run: () => Promise<Snapshot | ControlResult>, success?: string) => Promise<boolean>;
