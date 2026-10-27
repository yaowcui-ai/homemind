import { Alert, Button, Tag } from 'antd';
import type { ActionView, TaskDetail as Detail } from '../../api/tasks.types';
import { scenarioLabels, statusLabels } from './labels';
import styles from './Tasks.module.css';

const outcomeLabels: Record<string, string> = { planned: '待执行', submitted: '已提交', verified: '已核验', failed: '失败', unknown: '未知', skipped: '未执行', pending: '待核验' };
function target(action: ActionView) {
  const p = action.parameters;
  if (action.action === 'set_light') return p.power === false ? '关闭灯光' : `打开灯光 · 亮度 ${p.brightness_pct}%`;
  if (action.action === 'set_climate') return p.mode === 'off' ? '关闭空调' : `制冷至 ${p.target_temperature_c}℃ · ${p.fan_mode === 'low' ? '低速风' : '自动风速'}`;
  if (action.action === 'set_cover') return `设置窗帘开度 ${p.position_pct}%`;
  return '设置设备目标';
}
export default function TaskDetail({ task, pending, onVerify }: { task: Detail; pending: boolean; onVerify: () => void }) {
  return <section className={styles.card} aria-label="任务详情">
    <div className={styles.sectionHead}><h2>{scenarioLabels[task.scenario]}</h2><Tag color={task.status === 'succeeded' ? 'green' : task.status === 'failed' ? 'red' : 'gold'}>{statusLabels[task.status]}</Tag></div>
    <Alert type={task.status === 'succeeded' ? 'success' : task.status === 'failed' ? 'error' : 'info'} title={task.message} />
    <p className={styles.hint}>任务编号 {task.id}</p>
    <h3>动作与读回</h3>
    {!task.actions.length && <p className={styles.hint}>没有可执行动作。请查看下方条件说明。</p>}
    {task.actions.map((action) => <div className={styles.action} key={action.id}>
      <div><strong>{action.entity_name}</strong><small>{target(action)}</small><small>{action.room_name} · {action.message}</small>
        {action.transport_outcome === 'unknown' && <small>设备响应未知，以上结果来自独立读回。</small>}</div>
      <Tag color={action.status === 'verified' ? 'green' : 'orange'}>{outcomeLabels[action.status]}</Tag>
    </div>)}
    <h3>目标核验</h3>
    <p className={styles.hint}>核验时刻 t+{task.verification.checked_at_minutes} 分钟{task.verification.due_at_minutes !== null && ` · 目标时刻 t+${task.verification.due_at_minutes} 分钟`}。设备设置成功与室温达标分别判断。</p>
    {task.verification.conditions.map((condition, index) => <div className={styles.condition} key={`${index}-${condition.label}`}>
      <div><strong>{condition.label}</strong><small>{condition.message}</small></div><Tag>{outcomeLabels[condition.outcome]}</Tag>
    </div>)}
    {['waiting_verification', 'partial', 'failed'].includes(task.status) && <Button aria-label="核验目标" onClick={onVerify} loading={pending}>核验目标</Button>}
    <p className={styles.hint}>初始 t+{task.initial_snapshot.simulated_minutes} 分钟 → 结果 t+{task.final_snapshot.simulated_minutes} 分钟 · 累计仿真能耗 {task.final_snapshot.energy_wh.toFixed(3)} Wh</p>
  </section>;
}
