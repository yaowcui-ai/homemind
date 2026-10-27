import { useState } from 'react';
import { BorderOutlined, BulbOutlined, CloudOutlined, ControlOutlined, DashboardOutlined, EditOutlined, TeamOutlined, WindowsOutlined } from '@ant-design/icons';
import { Button, InputNumber, Select, Switch, Tag } from 'antd';
import { simulationApi } from '../../api/simulation';
import type { ControlInput, EntityView } from '../../api/simulation.types';
import type { Operation } from './labels';
import { entityLabels, isSensor } from './labels';
import styles from './Simulation.module.css';

const entityIcons = { light: BulbOutlined, climate: CloudOutlined, cover: BorderOutlined, temperature: DashboardOutlined, occupancy: TeamOutlined, window: WindowsOutlined };

export interface EntityCardProps {
  entity: EntityView;
  worldId: string;
  run: Operation;
  pending: boolean;
  debugEnabled?: boolean;
  onEdit: (entity: EntityView) => void;
  onFault: (entity: EntityView) => void;
}

export default function EntityCard({ entity, worldId, run, pending, onEdit, onFault, debugEnabled = false }: EntityCardProps) {
  const [lightOn, setLightOn] = useState(entity.state.power === true);
  const [brightness, setBrightness] = useState(Number(entity.state.brightness_pct) || Number(entity.config.default_brightness_pct) || 60);
  const [mode, setMode] = useState(entity.state.mode === 'cool' ? 'cool' : 'off');
  const [temperature, setTemperature] = useState(Number(entity.state.target_temperature_c) || Number(entity.config.initial_target_temperature_c) || 26);
  const [fan, setFan] = useState(entity.state.fan_mode === 'low' ? 'low' : 'auto');
  const [position, setPosition] = useState(typeof entity.state.position_pct === 'number' ? entity.state.position_pct : 100);
  const [sensorTemperature, setSensorTemperature] = useState(typeof entity.state.temperature_c === 'number' ? entity.state.temperature_c : 27);
  const sensor = isSensor(entity.type);
  const Icon = entityIcons[entity.type];
  const observed = entity.enabled && entity.available && entity.known;
  const writable = !pending && entity.enabled && entity.available && entity.pending_until_minutes === null;
  let value = '未知';
  if (observed) {
    if (entity.type === 'light' && typeof entity.state.power === 'boolean') value = entity.state.power ? `已开启 · ${entity.state.brightness_pct}%` : '已关闭';
    if (entity.type === 'climate' && typeof entity.state.mode === 'string') value = entity.state.mode === 'off' ? '已关闭' : `制冷 · 目标 ${entity.state.target_temperature_c}℃`;
    if (entity.type === 'cover' && typeof entity.state.position_pct === 'number') value = `开度 ${entity.state.position_pct}%`;
    if (entity.type === 'temperature' && typeof entity.state.temperature_c === 'number') value = `${entity.state.temperature_c.toFixed(1)}℃`;
    if (entity.type === 'occupancy' && typeof entity.state.occupied === 'boolean') value = entity.state.occupied ? '有人' : '无人';
    if (entity.type === 'window' && typeof entity.state.window_open === 'boolean') value = entity.state.window_open ? '窗户打开' : '窗户关闭';
  }

  function apply() {
    let input: ControlInput;
    if (entity.type === 'light') input = { action: 'set_light', parameters: { power: lightOn && brightness > 0, brightness_pct: lightOn ? brightness : 0 } };
    else if (entity.type === 'climate') input = { action: 'set_climate', parameters: { mode, target_temperature_c: temperature, fan_mode: fan } };
    else input = { action: 'set_cover', parameters: { position_pct: position } };
    void run(() => simulationApi.control(entity.id, { ...input, expected_world_id: worldId }));
  }

  return (
    <article className={`${styles.entityCard} ${sensor ? styles.sensorCard : ''}`} aria-label={entity.name}>
      <div className={styles.entityHead}>
        <span className={styles.entityIcon}><Icon /></span>
        <div className={styles.entityIdentity}><h3>{entity.name}</h3><span>{entityLabels[entity.type]}</span></div>
        <Tag color={!entity.enabled ? 'default' : !entity.available || !entity.known ? 'orange' : 'cyan'}>{!entity.enabled ? '停用' : !entity.available ? '离线' : !entity.known ? '读数未知' : '在线'}</Tag>
      </div>
      <div className={styles.entityValue} aria-live="polite">{value}</div>
      <div className={styles.entityMeta}>
        <span>{sensor ? '只读传感' : '当前状态 · 独立读回'}</span>
        <span>{sensor ? `第 ${entity.observed_at_minutes} 分钟读数` : `${entity.energy_wh.toFixed(3)} Wh`}</span>
      </div>
      {entity.pending_until_minutes !== null && <p className={styles.pendingNote}>待第 {entity.pending_until_minutes} 分钟生效</p>}
      {!sensor && <div className={styles.controlForm}>
        <span className={styles.controlHint}>目标设置 · 点击应用后生效</span>
        {entity.type === 'light' && <div className={styles.lightControls}>
          <label className={styles.switchLabel}>电源<Switch checked={lightOn} onChange={setLightOn} checkedChildren="开" unCheckedChildren="关" aria-label={`${entity.name}目标开关`} disabled={!writable} /></label>
          <label className={styles.fieldLabel}>亮度（%）<InputNumber aria-label={`${entity.name}亮度`} min={0} max={100} precision={0} value={brightness} onChange={(v) => setBrightness(v ?? 0)} disabled={!writable} suffix="%" /></label>
        </div>}
        {entity.type === 'climate' && <>
          <div className={styles.controlRow}>
            <label className={styles.fieldLabel}>模式<Select aria-label={`${entity.name}模式`} value={mode} onChange={setMode} disabled={!writable} options={[{ value: 'off', label: '关闭' }, { value: 'cool', label: '制冷' }]} /></label>
            <label className={styles.fieldLabel}>温度（℃）<InputNumber aria-label={`${entity.name}目标温度`} min={16} max={30} precision={0} value={temperature} onChange={(v) => setTemperature(v ?? 26)} disabled={!writable} suffix="℃" /></label>
          </div>
          <label className={styles.fieldLabel}>风速<Select aria-label={`${entity.name}风速`} value={fan} onChange={setFan} disabled={!writable} options={[{ value: 'auto', label: '自动风速' }, { value: 'low', label: '低速风' }]} /></label>
        </>}
        {entity.type === 'cover' && <label className={styles.positionLabel}>目标开度 <InputNumber aria-label={`${entity.name}开度`} min={0} max={100} precision={0} value={position} onChange={(v) => setPosition(v ?? 0)} disabled={!writable} suffix="%" /></label>}
        <Button block type="primary" onClick={apply} disabled={!writable}>应用设置</Button>
      </div>}
      {sensor && debugEnabled && <div className={styles.sensorControls}>
        <span className={styles.controlHint}>模拟事件 · 不属于设备控制</span>
        {entity.type === 'temperature' && <div className={styles.controlRow}>
          <InputNumber aria-label={`${entity.name}模拟温度`} min={0} max={50} step={0.1} value={sensorTemperature} onChange={(v) => setSensorTemperature(v ?? 27)} disabled={pending || !entity.enabled} />
          <Button disabled={pending || !entity.enabled} onClick={() => { void run(() => simulationApi.event({ entity_id: entity.id, temperature_c: sensorTemperature }), '已注入温度事件'); }}>模拟温度</Button>
        </div>}
        {entity.type === 'occupancy' && <div className={styles.twoButtons}>
          <Button disabled={pending || !entity.enabled} onClick={() => { void run(() => simulationApi.event({ entity_id: entity.id, occupied: true }), '已模拟人员进入'); }}>模拟有人</Button>
          <Button disabled={pending || !entity.enabled} onClick={() => { void run(() => simulationApi.event({ entity_id: entity.id, occupied: false }), '已模拟人员离开'); }}>模拟无人</Button>
        </div>}
        {entity.type === 'window' && <div className={styles.twoButtons}>
          <Button disabled={pending || !entity.enabled} onClick={() => { void run(() => simulationApi.event({ entity_id: entity.id, window_open: true }), '已模拟窗户打开'); }}>模拟开窗</Button>
          <Button disabled={pending || !entity.enabled} onClick={() => { void run(() => simulationApi.event({ entity_id: entity.id, window_open: false }), '已模拟窗户关闭'); }}>模拟关窗</Button>
        </div>}
      </div>}
      <div className={styles.entityActions}>
        <Button type="text" size="small" aria-label="编辑实体" icon={<EditOutlined />} disabled={pending} onClick={() => onEdit(entity)}>编辑</Button>
        {debugEnabled && <Button type="text" size="small" aria-label="故障设置" icon={<ControlOutlined />} disabled={pending} onClick={() => onFault(entity)}>故障设置</Button>}
      </div>
    </article>
  );
}
