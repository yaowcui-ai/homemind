import { useState } from 'react';
import { Button, Drawer, InputNumber, Select, Switch } from 'antd';
import { simulationApi } from '../../api/simulation';
import type { EntityView, FaultMode } from '../../api/simulation.types';
import { faultDescriptions, faultLabels } from './labels';
import type { Operation } from './labels';
import styles from './Simulation.module.css';

interface Props { entity: EntityView; run: Operation; pending: boolean; onClose: () => void }

export default function FaultPanel({ entity, run, pending, onClose }: Props) {
  const [mode, setMode] = useState<FaultMode>(entity.fault.mode);
  const [delay, setDelay] = useState(entity.fault.delay_minutes);
  return <Drawer title={`${entity.name} · 故障设置`} open onClose={onClose} size={390}>
    <div className={styles.faultForm}>
      <p className={styles.formHint}>仅修改当前本地仿真。故障持续到清除，延迟通过推进仿真时间生效。</p>
      <label>故障类型<Select aria-label="故障类型" value={mode} onChange={setMode} options={Object.entries(faultLabels).map(([value, label]) => ({ value, label }))} /></label>
      <p className={styles.faultDescription}>{faultDescriptions[mode]}</p>
      {mode === 'delayed' && <label>延迟分钟<InputNumber aria-label="延迟分钟" min={1} max={60} precision={0} value={delay} onChange={(v) => setDelay(v ?? 2)} /></label>}
      <Button type="primary" disabled={pending} onClick={async () => { if (await run(() => simulationApi.setFault(entity.id, mode, delay), '故障规则已更新')) onClose(); }}>应用故障规则</Button>
      <div className={styles.qualityRow}><span>连接可用</span><Switch aria-label="连接可用" checked={entity.available} disabled={pending || entity.fault.mode === 'offline'} onChange={(available) => { void run(() => simulationApi.event({ entity_id: entity.id, available }), '连接状态已更新'); }} /></div>
      <div className={styles.qualityRow}><span>读数已知</span><Switch aria-label="读数已知" checked={entity.known} disabled={pending} onChange={(known) => { void run(() => simulationApi.event({ entity_id: entity.id, known }), '数据质量已更新'); }} /></div>
      <p className={styles.formHint}>信号未知或离线不会被当作无人、关窗或 0℃。清除离线故障后才可恢复连接。</p>
    </div>
  </Drawer>;
}
