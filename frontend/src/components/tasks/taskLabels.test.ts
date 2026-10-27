import { expect, it } from 'vitest';
import { actionTarget } from './taskLabels';
import type { PlannedAction } from '../../api/tasks.types';

const action = (name: string, parameters: PlannedAction['parameters']): PlannedAction => ({
  entity_id: 'entity-1', entity_name: '设备', room_name: '客厅', action: name, parameters,
});
it('局部空调只改风速，不虚构温度或开启制冷', () => {
  const label = actionTarget(action('set_climate', { fan_mode: 'low' }));
  expect(label).toBe('低速风');
  expect(label).not.toMatch(/undefined|制冷|自动/);
});
it('局部空调只改目标温度，不虚构风速或模式', () => {
  expect(actionTarget(action('set_climate', { target_temperature_c: 27 }))).toBe('目标温度 27℃');
});
it('正亮度按真实执行器语义打开灯光并展示亮度', () => {
  expect(actionTarget(action('set_light', { brightness_pct: 40 }))).toBe('打开灯光 · 亮度 40%');
});
const zeroBrightness: PlannedAction['parameters'][] = [{ brightness_pct: 0 }, { power: true, brightness_pct: 0 }];
it.each(zeroBrightness)('亮度0按真实执行器语义关闭灯，不因power字段误报开灯：%j', (parameters) => {
  expect(actionTarget(action('set_light', parameters))).toBe('关闭灯光 · 亮度 0%');
});
